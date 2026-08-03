"""Tamper-evident audit chain over case_events.

Every state change in CaseZero is an append-only event whose hash commits to the
hash before it. Altering any historical row breaks every hash after it, so the
chain does not merely record history — it proves history was not rewritten.

That is the honest answer to a bank's audit question: not "we log everything"
(everyone says that), but "here is the row where the record was altered."

The database also refuses UPDATE and DELETE on case_events (see
db/migrations/001_init.sql), so the only way to tamper is with the service role —
precisely the trusted-insider threat a hash chain exists to expose.

Deterministic and LLM-free. Covered by api/tests/test_chain.py.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

#: prev_hash of the first event in a case.
GENESIS_HASH = "0" * 64


def canonical_json(payload: Any) -> str:
    """Serialise deterministically.

    Hashing is only meaningful if the same logical payload always produces the
    same bytes, so keys are sorted, whitespace is fixed, and non-ASCII is kept
    literal rather than escaped.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def compute_hash(prev_hash: str, payload: Any) -> str:
    """sha256(prev_hash || canonical_json(payload))."""
    material = f"{prev_hash}{canonical_json(payload)}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True)
class ChainEvent:
    """One link. Mirrors a case_events row."""

    seq: int
    event_type: str
    actor: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


def build_event(
    seq: int,
    event_type: str,
    actor: str,
    payload: dict[str, Any],
    prev_hash: str,
) -> ChainEvent:
    """Construct the next link. The caller persists it; this stays pure so the
    hash logic is testable without a database."""
    return ChainEvent(
        seq=seq,
        event_type=event_type,
        actor=actor,
        payload=payload,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, payload),
    )


def append(
    events: Sequence[ChainEvent],
    event_type: str,
    actor: str,
    payload: dict[str, Any],
) -> ChainEvent:
    """Build the link that follows an existing chain."""
    if not events:
        return build_event(1, event_type, actor, payload, GENESIS_HASH)
    last = events[-1]
    return build_event(last.seq + 1, event_type, actor, payload, last.hash)


@dataclass(frozen=True)
class ChainVerdict:
    """Result of verifying a chain.

    `first_bad_seq` is the point the UI marks — the VOID pantograph blooms from
    exactly this row, the same way a cheque reveals the altered field rather than
    just declaring itself invalid.
    """

    ok: bool
    first_bad_seq: int | None = None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.ok


def verify_chain(events: Iterable[ChainEvent]) -> ChainVerdict:
    """Walk the chain and return the FIRST broken link.

    Detects three distinct failures, because they mean different things to an
    auditor: a rewritten payload, a re-parented link, and a removed event.
    """
    expected_prev = GENESIS_HASH
    expected_seq = 1

    for event in events:
        if event.seq != expected_seq:
            return ChainVerdict(
                ok=False,
                first_bad_seq=event.seq,
                reason=(
                    f"Sequence gap: expected event {expected_seq}, found {event.seq}. "
                    "An event was removed or reordered."
                ),
            )
        if event.prev_hash != expected_prev:
            return ChainVerdict(
                ok=False,
                first_bad_seq=event.seq,
                reason=(
                    f"Broken link at event {event.seq}: prev_hash does not match "
                    "the preceding event's hash."
                ),
            )
        recomputed = compute_hash(event.prev_hash, event.payload)
        if recomputed != event.hash:
            return ChainVerdict(
                ok=False,
                first_bad_seq=event.seq,
                reason=(
                    f"Payload altered at event {event.seq}: stored hash does not "
                    "match a hash recomputed from the payload."
                ),
            )
        expected_prev = event.hash
        expected_seq += 1

    return ChainVerdict(ok=True)


def chain_fingerprint(events: Sequence[ChainEvent]) -> str:
    """Head hash of the chain — the single value that attests to the whole case.

    Rendered as the hash strip in the UI and printed on the FMOS Referral Pack so
    the ombudsman can verify the file was not edited after submission.
    """
    return events[-1].hash if events else GENESIS_HASH
