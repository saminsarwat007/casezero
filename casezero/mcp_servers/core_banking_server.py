"""core-banking — a real MCP server over stdio.

Run standalone:
    python -m mcp_servers.core_banking_server

Or inspect it with any MCP client:
    npx @modelcontextprotocol/inspector python -m mcp_servers.core_banking_server

This is a genuine protocol server, not a Python module renamed "MCP". The verifier
and resolver agents discover these tools at runtime through an MCP session, which
is what the brief asks for when it says core system verification "using MCP".

The interesting property is that `post_adjustment` refuses without a signed
authorisation ticket from the compliance kernel. Hand this server to a hostile
agent and it still cannot move money.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from api.db.client import get_db
from api.kernel.tickets import TicketError
from api.mcp_tools import core_banking as tools

mcp = FastMCP(
    "core-banking",
    instructions=(
        "Read-only access to accounts and transactions, plus an authorised write "
        "path for reversals and credit adjustments. Postings require a signed "
        "authorisation ticket minted by the CaseZero compliance kernel after a PASS "
        "verification; calls without one are refused."
    ),
)


@mcp.tool()
def get_account(account_no: str) -> dict[str, Any]:
    """Account status, product type and current balance. The number is returned masked."""
    return tools.get_account(get_db(), account_no)


@mcp.tool()
def list_transactions(account_no: str, limit: int = 20) -> dict[str, Any]:
    """Recent transactions on an account, newest first."""
    return tools.list_transactions(get_db(), account_no, limit=limit)


@mcp.tool()
def find_transaction(txn_ref: str) -> dict[str, Any]:
    """Look up a single transaction by its reference."""
    return tools.find_transaction(get_db(), txn_ref)


@mcp.tool()
def verify_claim(
    account_no: str,
    amount_rm: float | None = None,
    txn_ref: str | None = None,
    merchant: str | None = None,
    tolerance_pct: float = 1.0,
    required_evidence: list[str] | None = None,
) -> dict[str, Any]:
    """Cross-reference a dispute against core banking.

    Returns PASS, FAIL or MANUAL_REVIEW with the rows and reasoning behind the
    verdict. FAIL means the record contradicts the claim; MANUAL_REVIEW means the
    record is silent or ambiguous and a person must decide.
    """
    return tools.verify_claim(
        get_db(),
        account_no=account_no,
        amount_rm=amount_rm,
        txn_ref=txn_ref,
        merchant=merchant,
        tolerance_pct=tolerance_pct,
        required_evidence=required_evidence or [],
    )


@mcp.tool()
def post_adjustment(
    case_id: str,
    account_no: str,
    entry_type: str,
    debit_account: str,
    amount_rm: float,
    narrative: str,
    posted_by: str,
    authorisation: str,
    dual_control_by: str | None = None,
    txn_ref: str | None = None,
) -> dict[str, Any]:
    """Post a balanced REVERSAL or CREDIT_ADJUSTMENT to a customer account.

    `authorisation` is a ticket issued by the compliance kernel. It is bound to
    this case, account, amount and entry type, so it cannot be replayed elsewhere
    or presented for a larger sum.
    """
    try:
        return tools.post_adjustment(
            get_db(),
            case_id=case_id,
            account_no=account_no,
            entry_type=entry_type,
            debit_account=debit_account,
            amount_rm=amount_rm,
            narrative=narrative,
            posted_by=posted_by,
            authorisation=authorisation,
            dual_control_by=dual_control_by,
            txn_ref=txn_ref,
        )
    except TicketError as exc:
        # Surfaced as a refusal with a reason rather than a stack trace: the agent
        # should report it to a human, not retry it.
        return {"posted": False, "refused": True, "reason": str(exc)}


@mcp.tool()
def get_ledger(case_id: str) -> dict[str, Any]:
    """Every journal entry posted for a case, with the balance recomputed."""
    return tools.get_ledger(get_db(), case_id)


if __name__ == "__main__":
    asyncio.run(mcp.run_stdio_async())
