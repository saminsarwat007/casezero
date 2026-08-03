"""crm — a real MCP server over stdio.

Run standalone:
    python -m mcp_servers.crm_server

The second server exists because the questions it answers are the ones that change
the answer. `customer_segment` and `is_repeat_complaint` are what promote a small
dispute to High urgency in every rule pack, and they belong to a system of record
rather than to the model's impression of an email's tone.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from api.db.client import get_db
from api.mcp_tools import crm as tools

mcp = FastMCP(
    "crm",
    instructions=(
        "Customer profile, segment and complaint history. Supplies the facts the "
        "compliance kernel evaluates when assigning urgency. NRICs are returned "
        "masked; plaintext never leaves the database."
    ),
)


@mcp.tool()
def get_customer_by_account(account_no: str) -> dict[str, Any]:
    """Resolve an account number to the customer who holds it."""
    return tools.get_customer_by_account(get_db(), account_no)


@mcp.tool()
def get_customer(customer_id: str) -> dict[str, Any]:
    """Customer profile by id: segment, vulnerability flag and risk markers."""
    return tools.get_customer(get_db(), customer_id)


@mcp.tool()
def get_complaint_history(
    customer_id: str,
    category: str | None = None,
    exclude_case_id: str | None = None,
) -> dict[str, Any]:
    """Prior complaints for a customer, and whether this one is a repeat."""
    return tools.get_complaint_history(
        get_db(),
        customer_id=customer_id,
        category=category,
        exclude_case_id=exclude_case_id,
    )


@mcp.tool()
def get_case_facts(
    account_no: str,
    category: str | None = None,
    exclude_case_id: str | None = None,
) -> dict[str, Any]:
    """Every fact the urgency rules consume, in one call.

    The rule evaluator fails closed on a missing fact, so gathering them together
    avoids a case being quietly downgraded because one lookup was skipped.
    """
    return tools.get_case_facts(
        get_db(),
        account_no=account_no,
        category=category,
        exclude_case_id=exclude_case_id,
    )


if __name__ == "__main__":
    asyncio.run(mcp.run_stdio_async())
