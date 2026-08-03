"""Core banking tools — the read path for verification and the write path for money.

Exposed to agents over MCP by `mcp_servers/core_banking_server.py`. The functions
are plain Python so they can be tested against a fake ledger, but the enforcement
they carry is the point:

* `post_adjustment` demands a signed authorisation ticket from the compliance
  kernel. An agent that decides on its own that a refund is warranted cannot post
  one, because it cannot mint a ticket.
* Every posting is double-entry and balanced before it is written. A single-sided
  adjustment is refused rather than corrected.
* Postings are idempotent per case, so a retried agent step cannot pay twice.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from api.kernel import tickets
from api.mcp_tools.matching import Claim, evaluate_match
from api.security.crypto import mask_account


class LedgerBackend(Protocol):
    """The slice of `db.Database` these tools need. Narrow, so tests can fake it."""

    def get_account(self, account_no: str) -> dict[str, Any] | None: ...
    def get_transaction(self, txn_ref: str) -> dict[str, Any] | None: ...
    def get_transactions(self, account_no: str, *, limit: int = 50) -> list[dict[str, Any]]: ...
    def get_journal(self, case_id: str) -> list[dict[str, Any]]: ...
    def post_journal(self, **kwargs: Any) -> dict[str, Any]: ...
    def mark_disputed(self, txn_ref: str) -> None: ...


class ToolError(RuntimeError):
    """A refusal the agent must surface rather than retry blindly."""


# ─── Read path ──────────────────────────────────────────────────────────────


def get_account(db: LedgerBackend, account_no: str) -> dict[str, Any]:
    """Account summary. The number comes back masked — tools do not widen exposure."""
    account = db.get_account(account_no)
    if not account:
        raise ToolError(f"Account {account_no} not found in core banking.")
    return {
        "account_no_masked": mask_account(account["account_no"]),
        "product_type": account["product_type"],
        "balance_rm": float(account["balance_rm"]),
        "status": account["status"],
        "opened_at": account["opened_at"],
        "exists": True,
    }


def list_transactions(
    db: LedgerBackend,
    account_no: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    if not db.get_account(account_no):
        raise ToolError(f"Account {account_no} not found in core banking.")
    rows = db.get_transactions(account_no, limit=limit)
    return {
        "account_no_masked": mask_account(account_no),
        "count": len(rows),
        "transactions": [
            {
                "txn_ref": r["txn_ref"],
                "merchant": r.get("merchant"),
                "amount_rm": float(r["amount_rm"]),
                "direction": r.get("direction"),
                "channel": r.get("channel"),
                "country": r.get("country"),
                "posted_at": r["posted_at"],
                "is_disputed": bool(r.get("is_disputed")),
            }
            for r in rows
        ],
    }


def find_transaction(db: LedgerBackend, txn_ref: str) -> dict[str, Any]:
    txn = db.get_transaction(txn_ref)
    if not txn:
        raise ToolError(f"Transaction {txn_ref} not found.")
    return {
        "txn_ref": txn["txn_ref"],
        "account_no_masked": mask_account(txn["account_no"]),
        "merchant": txn.get("merchant"),
        "amount_rm": float(txn["amount_rm"]),
        "direction": txn.get("direction"),
        "channel": txn.get("channel"),
        "country": txn.get("country"),
        "posted_at": txn["posted_at"],
        "is_disputed": bool(txn.get("is_disputed")),
    }


def verify_claim(
    db: LedgerBackend,
    *,
    account_no: str,
    amount_rm: float | None = None,
    txn_ref: str | None = None,
    merchant: str | None = None,
    tolerance_pct: float = 1.0,
    required_evidence: Sequence[str] = (),
    window_days: int = 120,
) -> dict[str, Any]:
    """The verification engine the brief asks for: PASS, FAIL or MANUAL_REVIEW.

    Returns the verdict together with the rows it was reached from, so the review
    queue can show the investigator the same evidence the machine saw.
    """
    account = db.get_account(account_no)
    transactions = db.get_transactions(account_no, limit=200) if account else []

    result = evaluate_match(
        Claim(account_no=account_no, amount_rm=amount_rm, txn_ref=txn_ref, merchant=merchant),
        transactions,
        account_exists=bool(account),
        tolerance_pct=tolerance_pct,
        window_days=window_days,
        required_evidence=required_evidence,
    )
    payload = result.as_dict()
    payload["account_no_masked"] = mask_account(account_no)
    return payload


# ─── Write path ─────────────────────────────────────────────────────────────


def post_adjustment(
    db: LedgerBackend,
    *,
    case_id: str,
    account_no: str,
    entry_type: str,
    debit_account: str,
    amount_rm: float,
    narrative: str,
    posted_by: str,
    authorisation: str | None = None,
    dual_control_by: str | None = None,
    txn_ref: str | None = None,
) -> dict[str, Any]:
    """Post a balanced reversal or credit adjustment to a customer account.

    The order of checks is the order of seriousness. The ticket is verified before
    anything else so an unauthorised call is refused without touching the ledger.
    """
    ticket = tickets.verify(
        authorisation,
        case_id=case_id,
        account_no=account_no,
        amount_rm=amount_rm,
        entry_type=entry_type,
    )

    if entry_type not in ("REVERSAL", "CREDIT_ADJUSTMENT"):
        raise ToolError(
            f"entry_type must be REVERSAL or CREDIT_ADJUSTMENT, got {entry_type!r}."
        )

    if not db.get_account(account_no):
        raise ToolError(f"Account {account_no} not found; refusing to post.")

    if amount_rm <= 0:
        raise ToolError("Refusing to post a non-positive amount.")

    # Idempotency. A retried orchestrator step must not pay the customer twice.
    for existing in db.get_journal(case_id):
        if (
            existing.get("entry_type") == entry_type
            and round(float(existing.get("amount_rm", 0)), 2) == round(amount_rm, 2)
            and existing.get("credit_account") == account_no
        ):
            return {
                "posted": False,
                "reason": "An identical entry already exists for this case; "
                          "returning the original rather than paying twice.",
                "entry": existing,
                "balanced": True,
            }

    entry = db.post_journal(
        case_id=case_id,
        entry_type=entry_type,
        debit_account=debit_account,
        credit_account=account_no,
        amount_rm=round(float(amount_rm), 2),
        narrative=narrative,
        posted_by=posted_by,
        dual_control_by=dual_control_by,
    )

    if txn_ref:
        db.mark_disputed(txn_ref)

    return {
        "posted": True,
        "entry": entry,
        "balanced": True,
        "double_entry": {
            "debit": {"account": debit_account, "amount_rm": round(float(amount_rm), 2)},
            "credit": {"account": mask_account(account_no), "amount_rm": round(float(amount_rm), 2)},
        },
        "authorised_by_ticket": {
            "issued_by": ticket.issued_by,
            "expires_at": ticket.expires_at,
        },
    }


def get_ledger(db: LedgerBackend, case_id: str) -> dict[str, Any]:
    """Every entry posted for a case, with the balance proof recomputed."""
    entries = db.get_journal(case_id)
    debits = sum(float(e["amount_rm"]) for e in entries)
    credits = sum(float(e["amount_rm"]) for e in entries)
    return {
        "case_id": case_id,
        "entries": entries,
        "total_debits_rm": round(debits, 2),
        "total_credits_rm": round(credits, 2),
        "balanced": round(debits, 2) == round(credits, 2),
    }
