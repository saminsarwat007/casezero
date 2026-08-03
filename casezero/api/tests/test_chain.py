"""Tamper-evident audit chain.

The claim on stage is not "we log everything" — every team says that. The claim is
"here is the exact row where the record was altered." These tests are what make
that claim true, and the live tamper demo is just this suite run by hand.
"""

from dataclasses import replace

from api.kernel.chain import (
    GENESIS_HASH,
    ChainEvent,
    append,
    canonical_json,
    chain_fingerprint,
    compute_hash,
    verify_chain,
)


def sample_chain() -> list[ChainEvent]:
    """A realistic case history: received, classified, verified, resolved."""
    events: list[ChainEvent] = []
    for event_type, actor, payload in [
        ("CASE_RECEIVED", "agent:intake", {"channel": "IMAP", "amount_rm": 2450.00}),
        ("CASE_CLASSIFIED", "agent:classifier",
         {"category": "unauthorized_transaction", "urgency": "High", "confidence": 0.94}),
        ("CASE_VERIFIED", "agent:verifier",
         {"result": "PASS", "evidence": ["txn_ref_found", "amount_matches"]}),
        ("JOURNAL_POSTED", "agent:resolver",
         {"entry_type": "REVERSAL", "amount_rm": 2450.00}),
    ]:
        events.append(append(events, event_type, actor, payload))
    return events


class TestCanonicalisation:
    """Hashing is only meaningful if identical payloads produce identical bytes."""

    def test_key_order_does_not_change_the_serialisation(self):
        assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})

    def test_key_order_does_not_change_the_hash(self):
        assert compute_hash(GENESIS_HASH, {"b": 1, "a": 2}) == compute_hash(
            GENESIS_HASH, {"a": 2, "b": 1}
        )

    def test_hash_is_sensitive_to_value_changes(self):
        assert compute_hash(GENESIS_HASH, {"amount_rm": 2450.00}) != compute_hash(
            GENESIS_HASH, {"amount_rm": 2451.00}
        )

    def test_hash_depends_on_position_in_the_chain(self):
        payload = {"amount_rm": 2450.00}
        assert compute_hash(GENESIS_HASH, payload) != compute_hash("a" * 64, payload)


class TestConstruction:
    def test_first_event_links_to_genesis(self):
        events = sample_chain()
        assert events[0].seq == 1
        assert events[0].prev_hash == GENESIS_HASH

    def test_each_event_commits_to_its_predecessor(self):
        events = sample_chain()
        for previous, current in zip(events, events[1:]):
            assert current.prev_hash == previous.hash
            assert current.seq == previous.seq + 1

    def test_hashes_are_sha256_hex(self):
        for event in sample_chain():
            assert len(event.hash) == 64
            assert set(event.hash) <= set("0123456789abcdef")

    def test_fingerprint_is_the_head_hash(self):
        events = sample_chain()
        assert chain_fingerprint(events) == events[-1].hash

    def test_fingerprint_of_an_empty_chain_is_genesis(self):
        assert chain_fingerprint([]) == GENESIS_HASH


class TestVerification:
    def test_an_untouched_chain_verifies(self):
        verdict = verify_chain(sample_chain())
        assert verdict.ok
        assert verdict.first_bad_seq is None
        assert bool(verdict) is True

    def test_an_empty_chain_verifies(self):
        assert verify_chain([]).ok


class TestTamperDetection:
    """Three distinct attacks, because they mean different things to an auditor."""

    def test_rewriting_a_payload_is_caught_at_that_row(self):
        events = sample_chain()
        # An insider quietly inflates the refund on the resolution event.
        events[3] = replace(events[3], payload={"entry_type": "REVERSAL", "amount_rm": 99999.00})

        verdict = verify_chain(events)
        assert not verdict.ok
        assert verdict.first_bad_seq == 4
        assert "altered" in verdict.reason.lower()

    def test_tampering_early_is_reported_at_the_earliest_break(self):
        events = sample_chain()
        events[1] = replace(events[1], payload={"category": "billing_error"})

        verdict = verify_chain(events)
        assert not verdict.ok
        # Reported at the tampered row, not at some later cascade.
        assert verdict.first_bad_seq == 2

    def test_deleting_an_event_is_caught_as_a_sequence_gap(self):
        events = sample_chain()
        del events[2]  # try to erase the verification step

        verdict = verify_chain(events)
        assert not verdict.ok
        assert verdict.first_bad_seq == 4
        assert "removed" in verdict.reason.lower() or "gap" in verdict.reason.lower()

    def test_re_parenting_an_event_is_caught_as_a_broken_link(self):
        events = sample_chain()
        # Payload untouched and its hash recomputed, but spliced onto the wrong parent.
        forged_parent = "f" * 64
        events[2] = replace(
            events[2],
            prev_hash=forged_parent,
            hash=compute_hash(forged_parent, events[2].payload),
        )

        verdict = verify_chain(events)
        assert not verdict.ok
        assert verdict.first_bad_seq == 3
        assert "link" in verdict.reason.lower()

    def test_a_verdict_reason_is_always_human_readable(self):
        events = sample_chain()
        events[3] = replace(events[3], payload={"amount_rm": 1.00})
        verdict = verify_chain(events)
        # The reason is shown to a compliance officer, not just logged.
        assert verdict.reason
        assert "event 4" in verdict.reason.lower()

    def test_appending_after_a_tamper_cannot_repair_the_chain(self):
        events = sample_chain()
        events[1] = replace(events[1], payload={"category": "billing_error"})
        events.append(append(events, "CASE_CLOSED", "user:ops", {"note": "nothing to see"}))

        verdict = verify_chain(events)
        assert not verdict.ok
        assert verdict.first_bad_seq == 2
