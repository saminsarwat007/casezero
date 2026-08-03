"""The MCP tool surface.

The claim these tests defend is the one a bank's CISO will press on: *what stops an
agent from paying a customer whatever it likes?* The answer is not the prompt. It
is that `post_adjustment` verifies a signature it cannot produce.

Also covered: masking on every read, double-entry on every write, and idempotency,
because a retried agent step must not pay twice.
"""

import pytest

from api.kernel import tickets
from api.mcp_tools import core_banking as cb
from api.mcp_tools import crm
from api.mcp_tools.core_banking import ToolError


def ticket_for(bank, *, amount_rm=2450.00, entry_type="REVERSAL", **overrides):
    kwargs = dict(
        case_id=bank.CASE_ID,
        account_no=bank.ACCOUNT_NO,
        amount_rm=amount_rm,
        entry_type=entry_type,
        issued_by="kernel:gates",
    )
    kwargs.update(overrides)
    return tickets.issue(**kwargs)


def post(bank, **overrides):
    kwargs = dict(
        case_id=bank.CASE_ID,
        account_no=bank.ACCOUNT_NO,
        entry_type="REVERSAL",
        debit_account="GL-1450-FRAUD-SUSPENSE",
        amount_rm=2450.00,
        narrative="Reversal of unauthorised transaction TXN-88213.",
        posted_by="agent:resolver",
        authorisation=ticket_for(bank),
    )
    kwargs.update(overrides)
    return cb.post_adjustment(bank, **kwargs)


class TestReadPath:
    def test_an_account_comes_back_masked(self, bank):
        result = cb.get_account(bank, bank.ACCOUNT_NO)
        assert result["account_no_masked"] == "******6890"
        assert bank.ACCOUNT_NO not in str(result)
        assert result["balance_rm"] == 8412.55

    def test_an_unknown_account_is_a_refusal_not_an_empty_result(self, bank):
        """Returning {} would let a caller treat 'no such account' as 'no activity'."""
        with pytest.raises(ToolError, match="not found"):
            cb.get_account(bank, "0000000000")

    def test_transactions_are_listed_newest_first(self, bank):
        bank.transactions["TXN-99"] = {
            **bank.transactions["TXN-88213"],
            "txn_ref": "TXN-99",
            "posted_at": "2026-03-20T09:00:00+00:00",
        }
        listed = cb.list_transactions(bank, bank.ACCOUNT_NO)
        assert listed["count"] == 2
        assert listed["transactions"][0]["txn_ref"] == "TXN-99"

    def test_a_single_transaction_can_be_fetched_by_reference(self, bank):
        assert cb.find_transaction(bank, "TXN-88213")["amount_rm"] == 2450.00

    def test_verify_claim_returns_the_spec_vocabulary(self, bank):
        result = cb.verify_claim(
            bank, account_no=bank.ACCOUNT_NO, txn_ref="TXN-88213", amount_rm=2450.00
        )
        assert result["verdict"] == "PASS"
        assert result["matched"]["txn_ref"] == "TXN-88213"
        assert result["account_no_masked"] == "******6890"

    def test_verify_claim_fails_on_an_unknown_account(self, bank):
        assert cb.verify_claim(bank, account_no="0000000000")["verdict"] == "FAIL"


class TestAuthorisation:
    """The control that survives a hijacked agent."""

    def test_a_posting_without_a_ticket_is_refused(self, bank):
        with pytest.raises(tickets.TicketError, match="has not been authorised"):
            post(bank, authorisation=None)
        assert bank.journal == []

    def test_a_forged_ticket_is_refused(self, bank):
        with pytest.raises(tickets.TicketError, match="signature is invalid"):
            post(bank, authorisation="eyJhIjoxfQ.deadbeef")
        assert bank.journal == []

    def test_a_ticket_for_a_smaller_amount_cannot_be_stretched(self, bank):
        """An agent talked into inflating the refund still cannot post it."""
        small = ticket_for(bank, amount_rm=90.00)
        with pytest.raises(tickets.TicketError, match="amount"):
            post(bank, amount_rm=9000.00, authorisation=small)
        assert bank.journal == []

    def test_a_ticket_from_another_case_is_refused(self, bank):
        other = ticket_for(bank, case_id="c0000000-0000-0000-0000-000000000999")
        with pytest.raises(tickets.TicketError, match="case"):
            post(bank, authorisation=other)

    def test_a_valid_ticket_posts(self, bank):
        result = post(bank)
        assert result["posted"] is True
        assert result["authorised_by_ticket"]["issued_by"] == "kernel:gates"


class TestDoubleEntry:
    def test_a_posting_is_balanced_by_construction(self, bank):
        result = post(bank)
        pair = result["double_entry"]
        assert pair["debit"]["amount_rm"] == pair["credit"]["amount_rm"] == 2450.00
        assert pair["debit"]["account"] == "GL-1450-FRAUD-SUSPENSE"

    def test_the_credit_side_is_masked_in_the_response(self, bank):
        assert post(bank)["double_entry"]["credit"]["account"] == "******6890"

    def test_the_ledger_reports_itself_balanced(self, bank):
        post(bank)
        ledger = cb.get_ledger(bank, bank.CASE_ID)
        assert ledger["balanced"]
        assert ledger["total_debits_rm"] == 2450.00

    def test_an_unknown_entry_type_is_refused(self, bank):
        with pytest.raises(ToolError, match="REVERSAL or CREDIT_ADJUSTMENT"):
            post(
                bank,
                entry_type="WRITE_OFF",
                authorisation=ticket_for(bank, entry_type="WRITE_OFF"),
            )

    def test_posting_to_an_unknown_account_is_refused(self, bank):
        with pytest.raises(ToolError, match="refusing to post"):
            post(
                bank,
                account_no="0000000000",
                authorisation=ticket_for(bank, account_no="0000000000"),
            )

    def test_the_disputed_transaction_is_flagged_when_named(self, bank):
        post(bank, txn_ref="TXN-88213")
        assert bank.transactions["TXN-88213"]["is_disputed"] is True


class TestIdempotency:
    def test_a_retried_posting_does_not_pay_twice(self, bank):
        first = post(bank)
        second = post(bank)

        assert first["posted"] is True
        assert second["posted"] is False
        assert "already exists" in second["reason"]
        assert len(bank.journal) == 1

    def test_a_genuinely_different_amount_still_posts(self, bank):
        post(bank)
        post(bank, amount_rm=15.90, authorisation=ticket_for(bank, amount_rm=15.90))
        assert len(bank.journal) == 2


class TestCrm:
    def test_an_account_resolves_to_its_customer(self, bank):
        profile = crm.get_customer_by_account(bank, bank.ACCOUNT_NO)
        assert profile["name"].startswith("Nurul")
        assert profile["segment"] == "retail"
        assert profile["is_vulnerable"] is False
        assert profile["account_no_masked"] == "******6890"

    def test_an_nric_is_never_returned_in_full(self, bank):
        profile = crm.get_customer_by_account(bank, bank.ACCOUNT_NO)
        assert profile["nric_masked"].endswith("****")

    def test_a_vulnerable_segment_is_surfaced_as_a_fact(self, bank):
        bank.customers[bank.CUSTOMER_ID]["segment"] = "vulnerable"
        assert crm.get_customer_by_account(bank, bank.ACCOUNT_NO)["is_vulnerable"] is True

    def test_an_unrecognised_segment_degrades_to_retail(self, bank):
        """A junk value must not silently become a new urgency tier."""
        bank.customers[bank.CUSTOMER_ID]["segment"] = "platinum-elite"
        assert crm.get_customer_by_account(bank, bank.ACCOUNT_NO)["segment"] == "retail"

    def test_an_orphaned_account_escalates_rather_than_guessing(self, bank):
        bank.accounts[bank.ACCOUNT_NO]["customer_id"] = "missing"
        with pytest.raises(crm.ToolError, match="data integrity"):
            crm.get_customer_by_account(bank, bank.ACCOUNT_NO)

    def test_a_first_time_complainant_is_not_a_repeat(self, bank):
        history = crm.get_complaint_history(
            bank, customer_id=bank.CUSTOMER_ID, category="billing_error"
        )
        assert history["is_repeat_complaint"] is False
        assert history["total_complaints"] == 0

    def test_a_second_complaint_in_the_same_category_is_a_repeat(self, bank):
        """The fact that promotes a small billing error to High urgency."""
        bank.cases.append(
            {
                "id": "old",
                "case_ref": "MYB-2026-000001",
                "customer_id": bank.CUSTOMER_ID,
                "category": "billing_error",
                "status": "CLOSED",
                "outcome": "RESOLVED_IN_FULL",
                "amount_rm": 45.00,
                "created_at": "2026-01-04T00:00:00+00:00",
            }
        )
        history = crm.get_complaint_history(
            bank, customer_id=bank.CUSTOMER_ID, category="billing_error"
        )
        assert history["is_repeat_complaint"] is True
        assert history["same_category_count"] == 1

    def test_the_current_case_is_excluded_from_its_own_history(self, bank):
        bank.cases.append(
            {
                "id": bank.CASE_ID,
                "case_ref": "MYB-2026-000002",
                "customer_id": bank.CUSTOMER_ID,
                "category": "billing_error",
                "status": "RECEIVED",
                "created_at": "2026-03-14T00:00:00+00:00",
            }
        )
        history = crm.get_complaint_history(
            bank,
            customer_id=bank.CUSTOMER_ID,
            category="billing_error",
            exclude_case_id=bank.CASE_ID,
        )
        assert history["is_repeat_complaint"] is False

    def test_case_facts_return_exactly_what_the_urgency_rules_consume(self, bank, pack):
        facts = crm.get_case_facts(bank, account_no=bank.ACCOUNT_NO)
        # The evaluator fails closed on missing facts, so this is a contract test.
        assert "customer_segment" in facts
        assert "is_repeat_complaint" in facts
        assert pack.assign_urgency({**facts, "amount_rm": 2450.00}).urgency == "Medium"

    def test_case_facts_drive_the_vulnerable_override(self, bank, pack):
        bank.customers[bank.CUSTOMER_ID]["segment"] = "vulnerable"
        facts = crm.get_case_facts(bank, account_no=bank.ACCOUNT_NO)
        assert pack.assign_urgency({**facts, "amount_rm": 90.00}).urgency == "High"
