"""FMOS export is readable and carries the chain-verification evidence."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from api.reports.fmos_pack import build_fmos_pack


def test_fmos_pack_contains_case_journal_and_integrity(fake_db) -> None:
    case = fake_db.create_case(
        case_ref="MYB-2026-900001",
        status="COMMUNICATED",
        outcome="RESOLVED_IN_FULL",
        category="unauthorized_transaction",
        urgency="High",
        amount_rm=890,
        account_last4="6890",
        summary="Synthetic disputed debit.",
        verification_result="PASS",
        confidence=0.94,
        rule_pack_version=1,
        txn_refs=["SYN-1"],
    )
    fake_db.append_event(case["id"], "CASE_RECEIVED", "agent:intake", {"synthetic": True})
    fake_db.append_event(case["id"], "VERIFICATION_COMPLETED", "agent:verifier", {"result": "PASS"})
    fake_db.post_journal(
        case_id=case["id"],
        entry_type="REVERSAL",
        debit_account="GL-1450-FRAUD-SUSPENSE",
        credit_account="7142556890",
        amount_rm=890,
        narrative="Synthetic reversal.",
        posted_by="agent:resolver",
    )
    pdf = build_fmos_pack(
        case=case,
        events=fake_db.get_events(case["id"]),
        journal=fake_db.get_journal(case["id"]),
        verdict=fake_db.verify_case_chain(case["id"]),
        contact_email="complaints@mybank.com.my",
    )
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) == 4
    assert "MYB-2026-900001" in text
    assert "REVERSAL" in text
    assert "CHAIN VERIFIED" in text
    assert "HASH-CHAIN VERIFICATION" in text
    assert "7142556890" not in text
