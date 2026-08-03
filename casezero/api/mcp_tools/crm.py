"""CRM tools — who the customer is, and what we already know about them.

Exposed over MCP by `mcp_servers/crm_server.py`. This server exists because the
rule packs ask questions core banking cannot answer: is this customer vulnerable,
have they complained about this before, which language do they read.

Those are not decorations. `customer_segment: vulnerable` promotes a RM90 dispute
above a RM4,000 one in every pack, and `is_repeat_complaint` promotes a billing
error to High. The urgency the kernel assigns is only as good as the facts this
server returns, which is why they come from a system of record rather than from
the model's reading of the email.

NRICs never leave here in plaintext. The tool returns a masked form; the ciphertext
stays in the database.
"""

from __future__ import annotations

from typing import Any, Protocol

from api.security.crypto import mask_account, mask_nric

#: Segments the rule packs branch on. Anything else is treated as retail.
KNOWN_SEGMENTS = ("retail", "sme", "vulnerable", "senior", "priority")


class CrmBackend(Protocol):
    """The slice of `db.Database` these tools need."""

    def get_account(self, account_no: str) -> dict[str, Any] | None: ...
    def get_customer(self, customer_id: str) -> dict[str, Any] | None: ...
    def list_cases(self, *, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]: ...


class ToolError(RuntimeError):
    """A refusal the agent must surface rather than retry blindly."""


def _profile(customer: dict[str, Any]) -> dict[str, Any]:
    segment = str(customer.get("segment", "retail")).lower()
    flags = list(customer.get("risk_flags") or [])
    return {
        "customer_id": customer["id"],
        "name": customer["name"],
        "nric_masked": mask_nric(customer.get("nric_last4") and f"000000-00-{customer['nric_last4']}"),
        "nric_last4": customer.get("nric_last4"),
        "email": customer.get("email"),
        "segment": segment if segment in KNOWN_SEGMENTS else "retail",
        "is_vulnerable": segment == "vulnerable",
        "risk_flags": flags,
        "joined_at": customer.get("joined_at"),
    }


def get_customer_by_account(db: CrmBackend, account_no: str) -> dict[str, Any]:
    """Resolve an account number to the person behind it."""
    account = db.get_account(account_no)
    if not account:
        raise ToolError(f"Account {account_no} is not held by any customer on record.")

    customer = db.get_customer(account["customer_id"])
    if not customer:
        raise ToolError(
            f"Account {account_no} references customer {account['customer_id']}, "
            f"which does not exist. This is a data integrity problem, not a "
            f"customer problem — escalate rather than auto-resolving."
        )

    profile = _profile(customer)
    profile["account_no_masked"] = mask_account(account_no)
    profile["product_type"] = account.get("product_type")
    return profile


def get_customer(db: CrmBackend, customer_id: str) -> dict[str, Any]:
    customer = db.get_customer(customer_id)
    if not customer:
        raise ToolError(f"Customer {customer_id} not found.")
    return _profile(customer)


def get_complaint_history(
    db: CrmBackend,
    *,
    customer_id: str,
    category: str | None = None,
    exclude_case_id: str | None = None,
) -> dict[str, Any]:
    """Prior complaints, and the repeat-complaint fact the packs branch on.

    A customer raising the same category a second time is not making the same
    complaint twice — they are telling us the first resolution did not work. The
    packs treat that as a High-urgency signal, so it has to be a fact, not a
    sentiment the classifier picks up from an annoyed tone.
    """
    history = [
        case
        for case in db.list_cases(limit=500)
        if str(case.get("customer_id")) == str(customer_id)
        and str(case.get("id")) != str(exclude_case_id)
    ]

    same_category = [c for c in history if category and c.get("category") == category]
    unresolved = [c for c in history if c.get("status") not in ("CLOSED", "COMMUNICATED")]

    return {
        "customer_id": customer_id,
        "total_complaints": len(history),
        "same_category_count": len(same_category),
        "is_repeat_complaint": bool(same_category),
        "open_complaints": len(unresolved),
        "history": [
            {
                "case_ref": c.get("case_ref"),
                "category": c.get("category"),
                "status": c.get("status"),
                "outcome": c.get("outcome"),
                "amount_rm": float(c["amount_rm"]) if c.get("amount_rm") is not None else None,
                "created_at": c.get("created_at"),
            }
            for c in sorted(history, key=lambda c: c.get("created_at") or "", reverse=True)[:10]
        ],
    }


def get_case_facts(
    db: CrmBackend,
    *,
    account_no: str,
    category: str | None = None,
    exclude_case_id: str | None = None,
) -> dict[str, Any]:
    """One call returning exactly the facts `RulePack.assign_urgency` consumes.

    The urgency evaluator fails closed on a missing fact, so an agent assembling
    them field by field across several calls risks a silently-downgraded case.
    Gathering them in one place makes the fact set an explicit contract.
    """
    profile = get_customer_by_account(db, account_no)
    history = get_complaint_history(
        db,
        customer_id=profile["customer_id"],
        category=category,
        exclude_case_id=exclude_case_id,
    )
    return {
        "customer_id": profile["customer_id"],
        "customer_name": profile["name"],
        "customer_segment": profile["segment"],
        "is_repeat_complaint": history["is_repeat_complaint"],
        "open_complaints": history["open_complaints"],
        "risk_flags": profile["risk_flags"],
        "product_type": profile.get("product_type"),
    }
