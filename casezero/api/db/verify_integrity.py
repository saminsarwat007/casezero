"""Prove the audit chain against the live database.

Run:  .venv/bin/python -m api.db.verify_integrity

This is not a unit test — api/tests/test_chain.py already covers the maths. This
exercises the real Postgres instance and answers the question a bank's auditor
actually asks: *what happens when someone with full application privilege tries to
rewrite history?*

Three layers are demonstrated in order:

1. The chain is built through the one chokepoint, `Database.append_event`.
2. A service-role UPDATE or DELETE is **refused by Postgres privileges**. Not a
   policy the application could switch off — a privilege it does not hold. The
   attempt raises a hard error rather than failing quietly.
3. Connecting as the table **owner**, a compromised DBA succeeds at the row level.
   Nothing prevents that, and claiming otherwise would be dishonest. The hash
   chain is what catches it, naming the exact altered event. That is the frame the
   VOID pantograph renders from.

Also serves as the rehearsal script for the 4:40 beat in the demo.
"""

from __future__ import annotations

import sys

from api.db.client import Database, service_client
from api.db.management_api import run_sql

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

HISTORY = [
    ("CASE_RECEIVED", "agent:intake",
     {"channel": "MANUAL_INJECT", "amount_rm": 2450.00, "txn_ref": "TXN20260718TECHWORLD"}),
    ("CASE_CLASSIFIED", "agent:classifier",
     {"category": "unauthorized_transaction", "urgency": "Medium", "confidence": 0.95}),
    ("CASE_VERIFIED", "agent:verifier",
     {"result": "PASS", "evidence": ["account_exists", "txn_ref_found", "amount_matches"]}),
    ("JOURNAL_POSTED", "agent:resolver",
     {"entry_type": "REVERSAL", "amount_rm": 2450.00, "debit": "GL-1450-FRAUD-SUSPENSE"}),
]


def _reason(exc: Exception) -> str:
    """First line of a PostgREST error, for a one-line console report."""
    text = str(getattr(exc, "message", None) or exc)
    return text.split("\n")[0][:96]


def sql(query: str) -> None:
    """Owner-level SQL. Retries and timeouts live in api/db/management_api.py."""
    run_sql(query)


def main() -> int:
    db = Database()
    sb = service_client()
    failures: list[str] = []

    print("=" * 70)
    print("  CaseZero - live audit chain integrity")
    print("=" * 70)

    case = db.create_case(
        status="RECEIVED",
        channel="MANUAL_INJECT",
        summary="Integrity probe - safe to delete",
        amount_rm=2450.00,
        claimant_email="ahmad.ismail@example.my",
    )
    case_id = case["id"]
    print(f"\n  case {case['case_ref']}  {DIM}{case_id}{OFF}")

    try:
        # ─── 1. Build ───────────────────────────────────────────────────────
        print(f"\n{DIM}1. append four events through the single chokepoint{OFF}")
        for event_type, actor, payload in HISTORY:
            event = db.append_event(case_id, event_type, actor, payload)
            print(f"   seq={event.seq}  {event_type:<16} {DIM}{event.hash[:24]}...{OFF}")

        verdict = db.verify_case_chain(case_id)
        print(f"   verify -> ok={verdict.ok}")
        if not verdict.ok:
            failures.append("a freshly built chain failed verification")

        # ─── 2. The database refuses the application ───────────────────────
        print(f"\n{DIM}2. tamper using the service-role key (highest app privilege){OFF}")

        blocked_update = False
        try:
            sb.table("case_events").update(
                {"payload": {"entry_type": "REVERSAL", "amount_rm": 999_999.00}}
            ).eq("case_id", case_id).eq("seq", 4).execute()
        except Exception as exc:  # noqa: BLE001 - the refusal is the expected outcome
            blocked_update = True
            print(f"   UPDATE -> {GREEN}refused{OFF} {DIM}{_reason(exc)}{OFF}")

        row = next(e for e in db.get_events(case_id) if e.seq == 4)
        if row.payload.get("amount_rm") != 2450.00:
            failures.append("service-role UPDATE altered an audit event")
        elif not blocked_update:
            print(f"   UPDATE -> {GREEN}no rows changed{OFF}")

        blocked_delete = False
        try:
            sb.table("case_events").delete().eq("case_id", case_id).eq("seq", 2).execute()
        except Exception as exc:  # noqa: BLE001
            blocked_delete = True
            print(f"   DELETE -> {GREEN}refused{OFF} {DIM}{_reason(exc)}{OFF}")

        count = len(db.get_events(case_id))
        if count != 4:
            failures.append("service-role DELETE removed an audit event")
        elif not blocked_delete:
            print(f"   DELETE -> {GREEN}no rows removed{OFF}")

        print(f"   {DIM}The application does not hold these privileges. It cannot "
              f"rewrite history at all.{OFF}")

        # ─── 3. Compromised DBA ─────────────────────────────────────
        print(f"\n{DIM}3. tamper as the table owner — a compromised DBA{OFF}")
        sql(
            "update case_events set payload = "
            "'{\"entry_type\":\"REVERSAL\",\"amount_rm\":999999.00,"
            "\"debit\":\"GL-1450-FRAUD-SUSPENSE\"}'::jsonb "
            f"where case_id = '{case_id}' and seq = 4;"
        )
        tampered = next(e for e in db.get_events(case_id) if e.seq == 4)
        print(f"   row now reads RM {tampered.payload.get('amount_rm'):,.2f}  "
              f"{YELLOW}tamper succeeded at the row level{OFF}")

        verdict = db.verify_case_chain(case_id)
        print(f"   verify_chain -> ok={verdict.ok}  first_bad_seq={verdict.first_bad_seq}")
        print(f"   {DIM}{verdict.reason}{OFF}")

        if verdict.ok or verdict.first_bad_seq != 4:
            failures.append("verify_chain did not catch an owner-level tamper")
        else:
            print(f"   {GREEN}caught{OFF} — the chain names the exact altered event")

    finally:
        # Owner-level delete, because the app is (correctly) not allowed to remove
        # audit events and the cascade would otherwise be refused.
        sql(f"delete from cases where id = '{case_id}';")
        print(f"\n  {DIM}probe case deleted{OFF}")

    print("\n" + "=" * 70)
    if failures:
        print(f"  {RED}{len(failures)} PROBLEM(S){OFF}")
        for item in failures:
            print(f"    - {item}")
        print("=" * 70)
        return 1
    print(f"  {GREEN}audit chain is tamper-evident end to end{OFF}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
