"""Authorisation tickets: capabilities the kernel mints and the tools verify.

`kernel/gates.py` decides whether money may move. But a decision that lives only in
Python control flow is one refactor — or one hijacked agent — away from being
bypassed. So a `POST` ruling also mints a signed ticket, and the core-banking MCP
server refuses any posting that does not present a valid one.

That moves the guarantee across a process boundary. An agent that has been talked
into calling `post_adjustment` directly still cannot post, because it has no way to
forge the signature. The refusal comes from the tool, not from the model's manners.

A ticket is bound to five things — case, account, amount, entry type and expiry — so
it cannot be replayed against a different case, rounded up, or reused tomorrow.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, replace
from typing import Any, Mapping

from api.config import get_settings

#: Tickets are consumed seconds after they are minted; the window only needs to
#: cover the round trip to the MCP server.
DEFAULT_TTL_SECONDS = 120

#: Amounts are compared in sen to avoid float equality on money.
_SEN = 100


class TicketError(ValueError):
    """Raised when a ticket is absent, malformed, expired or does not match."""


def _secret() -> bytes:
    """Signing key, derived from the Fernet key so there is one secret to manage.

    Derived rather than reused directly: the same key material should not both
    encrypt PII and sign capabilities.
    """
    settings = get_settings()
    settings.require("fernet_key")
    return hashlib.sha256(b"casezero.ticket.v1|" + settings.fernet_key.encode()).digest()


def _canonical(claims: Mapping[str, Any]) -> bytes:
    return json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()


def _sign(claims: Mapping[str, Any]) -> str:
    digest = hmac.new(_secret(), _canonical(claims), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


@dataclass(frozen=True)
class Ticket:
    """A one-shot capability to post exactly one entry."""

    case_id: str
    account_no: str
    amount_sen: int
    entry_type: str
    issued_by: str
    expires_at: int
    signature: str = ""

    @property
    def amount_rm(self) -> float:
        return self.amount_sen / _SEN

    def claims(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "account_no": self.account_no,
            "amount_sen": self.amount_sen,
            "entry_type": self.entry_type,
            "issued_by": self.issued_by,
            "expires_at": self.expires_at,
        }

    def encode(self) -> str:
        payload = base64.urlsafe_b64encode(_canonical(self.claims())).decode().rstrip("=")
        return f"{payload}.{self.signature}"


def _b64decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def issue(
    *,
    case_id: str,
    account_no: str,
    amount_rm: float,
    entry_type: str,
    issued_by: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Mint a ticket. Only `gates.authorize_resolution` should call this."""
    if amount_rm <= 0:
        raise TicketError("Refusing to mint a ticket for a non-positive amount.")

    claims = Ticket(
        case_id=case_id,
        account_no=account_no,
        amount_sen=round(float(amount_rm) * _SEN),
        entry_type=entry_type,
        issued_by=issued_by,
        expires_at=int(time.time()) + ttl_seconds,
    )
    return replace(claims, signature=_sign(claims.claims())).encode()


def verify(
    token: str | None,
    *,
    case_id: str,
    account_no: str,
    amount_rm: float,
    entry_type: str,
) -> Ticket:
    """Check a ticket against the posting it is being used for.

    Every field is re-checked against the actual request rather than trusted from
    the token, so a valid ticket for RM90 cannot be presented for RM9,000.
    """
    if not token:
        raise TicketError(
            "No authorisation ticket was presented. The compliance kernel mints one "
            "only after a PASS verification and a threshold check, so a posting "
            "without a ticket has not been authorised."
        )

    payload, _, signature = token.partition(".")
    if not payload or not signature:
        raise TicketError("Malformed authorisation ticket.")

    try:
        claims = json.loads(_b64decode(payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TicketError("Authorisation ticket could not be decoded.") from exc

    if not hmac.compare_digest(signature, _sign(claims)):
        raise TicketError(
            "Authorisation ticket signature is invalid. It was not issued by this "
            "compliance kernel."
        )

    ticket = Ticket(**claims, signature=signature)

    if ticket.expires_at < int(time.time()):
        raise TicketError("Authorisation ticket has expired; re-run the gate.")

    expected_sen = round(float(amount_rm) * _SEN)
    mismatches: list[str] = []
    if ticket.case_id != case_id:
        mismatches.append(f"case {ticket.case_id} != {case_id}")
    if ticket.account_no != account_no:
        mismatches.append(f"account {ticket.account_no} != {account_no}")
    if ticket.amount_sen != expected_sen:
        mismatches.append(f"amount {ticket.amount_rm:.2f} != {float(amount_rm):.2f}")
    if ticket.entry_type != entry_type:
        mismatches.append(f"entry type {ticket.entry_type} != {entry_type}")

    if mismatches:
        raise TicketError(
            "Authorisation ticket does not match this posting: " + "; ".join(mismatches)
        )

    return ticket
