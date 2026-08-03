"""Proof that the MCP servers are real.

    python -m api.mcp_tools.smoke

Spawns both servers as subprocesses, completes an MCP handshake, *discovers* their
tools rather than assuming them, and exercises the read path, the verification
engine and the authorisation refusal.

The refusal is the one to watch. It is an agent calling `post_adjustment` with no
ticket, against a live server, and being told no by the tool.
"""

from __future__ import annotations

import asyncio
import sys

from api.config import get_settings
from api.kernel import tickets
from api.mcp_tools.gateway import StdioGateway, ToolCallError

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def ok(message: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {message}")


def fail(message: str) -> None:
    print(f"  {RED}FAIL{RESET}  {message}")


def head(message: str) -> None:
    print(f"\n{BOLD}{message}{RESET}")


async def main() -> int:
    settings = get_settings()
    settings.require("supabase_url", "supabase_service_role_key", "fernet_key")

    gateway = StdioGateway(settings)
    failures = 0

    try:
        head("1. Handshake and tool discovery")
        discovered = await gateway.list_tools()
        for server, names in discovered.items():
            print(f"  {DIM}{server}{RESET}: {', '.join(names)}")
        if len(discovered.get("core-banking", [])) >= 5 and discovered.get("crm"):
            ok("both servers completed an MCP initialize and advertised their tools")
        else:
            fail("tool discovery returned less than expected")
            failures += 1

        head("2. Read path over the protocol")
        accounts = await _first_seeded_account(gateway)
        if not accounts:
            fail("no seeded account found — run `python -m api.db.seed` first")
            return 1
        account_no, txn_ref, amount_rm = accounts

        account = await gateway.call("core-banking", "get_account", account_no=account_no)
        if account.get("account_no_masked", "").endswith(account_no[-4:]):
            ok(f"get_account returned {account['account_no_masked']} (masked at the tool)")
        else:
            fail(f"unexpected account payload: {account}")
            failures += 1

        head("3. Verification engine")
        verdict = await gateway.call(
            "core-banking",
            "verify_claim",
            account_no=account_no,
            txn_ref=txn_ref,
            amount_rm=amount_rm,
        )
        if verdict.get("verdict") in ("PASS", "FAIL", "MANUAL_REVIEW"):
            ok(f"verify_claim -> {verdict['verdict']}: {verdict['reasons'][0][:80]}")
        else:
            fail(f"unexpected verdict payload: {verdict}")
            failures += 1

        head("4. CRM facts that drive urgency")
        facts = await gateway.call("crm", "get_case_facts", account_no=account_no)
        if "customer_segment" in facts and "is_repeat_complaint" in facts:
            ok(
                f"segment={facts['customer_segment']} "
                f"repeat={facts['is_repeat_complaint']}"
            )
        else:
            fail(f"case facts incomplete: {facts}")
            failures += 1

        head("5. The control: posting without an authorisation ticket")
        refused = await gateway.call(
            "core-banking",
            "post_adjustment",
            case_id="00000000-0000-0000-0000-000000000000",
            account_no=account_no,
            entry_type="REVERSAL",
            debit_account="GL-1450-FRAUD-SUSPENSE",
            amount_rm=1.00,
            narrative="Smoke test — must be refused.",
            posted_by="agent:smoke",
            authorisation="forged.ticket",
        )
        if refused.get("refused") and not refused.get("posted"):
            ok(f"server refused: {refused['reason'][:90]}")
        else:
            fail(f"THE SERVER ACCEPTED AN UNAUTHORISED POSTING: {refused}")
            failures += 1

        head("6. A ticket bound to a different amount cannot be stretched")
        small = tickets.issue(
            case_id="00000000-0000-0000-0000-000000000000",
            account_no=account_no,
            amount_rm=1.00,
            entry_type="REVERSAL",
            issued_by="kernel:smoke",
        )
        stretched = await gateway.call(
            "core-banking",
            "post_adjustment",
            case_id="00000000-0000-0000-0000-000000000000",
            account_no=account_no,
            entry_type="REVERSAL",
            debit_account="GL-1450-FRAUD-SUSPENSE",
            amount_rm=9000.00,
            narrative="Smoke test — must be refused.",
            posted_by="agent:smoke",
            authorisation=small,
        )
        if stretched.get("refused"):
            ok(f"server refused: {stretched['reason'][:90]}")
        else:
            fail(f"A RM1 TICKET POSTED RM9,000: {stretched}")
            failures += 1

    except ToolCallError as exc:
        fail(str(exc))
        failures += 1
    finally:
        await gateway.aclose()

    print()
    if failures:
        print(f"{RED}{BOLD}{failures} check(s) failed.{RESET}")
    else:
        print(f"{GREEN}{BOLD}MCP servers verified over stdio.{RESET}")
    return 1 if failures else 0


async def _first_seeded_account(gateway: StdioGateway):
    """Find a real seeded account and one of its debits to test against."""
    from api.db.client import get_db

    db = get_db()
    accounts = db.sb.table("accounts").select("account_no").limit(20).execute().data
    for row in accounts:
        listing = await gateway.call(
            "core-banking", "list_transactions", account_no=row["account_no"], limit=10
        )
        for txn in listing.get("transactions", []):
            if txn.get("direction") == "DEBIT" and not txn.get("is_disputed"):
                return row["account_no"], txn["txn_ref"], txn["amount_rm"]
    return None


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
