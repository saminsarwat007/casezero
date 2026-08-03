"""The verification engine.

PASS, FAIL and MANUAL_REVIEW are the brief's words, and they have to mean three
different things or the queue fills with cases nobody needed to see. The boundary
under test:

* FAIL      — core banking contradicts the claim
* MANUAL_REVIEW — core banking is silent or ambiguous
* PASS      — exactly one row matches everything the customer stated
"""

from datetime import datetime, timedelta, timezone

import pytest

from api.mcp_tools.matching import (
    Claim,
    evaluate_match,
    merchant_matches,
    within_tolerance,
)

ACCOUNT = "7142556890"


def txn(**overrides):
    base = {
        "txn_ref": "TXN-88213",
        "account_no": ACCOUNT,
        "merchant": "TECHWORLD KL",
        "amount_rm": 2450.00,
        "direction": "DEBIT",
        "channel": "online",
        "country": "MY",
        "posted_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "is_disputed": False,
    }
    base.update(overrides)
    return base


def match(claim, transactions, **kwargs):
    kwargs.setdefault("account_exists", True)
    return evaluate_match(claim, transactions, **kwargs)


class TestTolerance:
    def test_an_exact_amount_always_matches(self):
        assert within_tolerance(2450.00, 2450.00, 1.0)

    def test_within_one_percent_matches(self):
        assert within_tolerance(2455.00, 2450.00, 1.0)

    def test_beyond_tolerance_does_not(self):
        assert not within_tolerance(2500.00, 2450.00, 1.0)

    def test_zero_tolerance_means_exact(self):
        """emoney_digital sets 0% because instant transfers settle to the sen."""
        assert within_tolerance(100.00, 100.00, 0.0)
        assert not within_tolerance(100.01, 100.00, 0.0)

    def test_a_wide_tolerance_covers_part_dispensed_cash(self):
        """atm_debit_card allows 10%: RM450 dispensed against a RM500 claim."""
        assert within_tolerance(500.00, 450.00, 12.0)


class TestMerchantMatching:
    @pytest.mark.parametrize(
        "claimed,actual",
        [
            ("Techworld", "TECHWORLD KL"),
            ("TECHWORLD KL*1234", "TECHWORLD KL"),
            ("techworld kl", "TechWorld KL"),
        ],
    )
    def test_a_customer_paraphrase_still_matches(self, claimed, actual):
        assert merchant_matches(claimed, actual)

    def test_a_different_merchant_does_not_match(self):
        assert not merchant_matches("Shopee", "TECHWORLD KL")

    def test_a_missing_name_is_not_a_match(self):
        assert not merchant_matches(None, "TECHWORLD KL")
        assert not merchant_matches("Techworld", None)


class TestFail:
    """Core banking contradicts the claim. Nothing for a human to weigh."""

    def test_an_unknown_account_fails(self):
        result = match(Claim(account_no="9999999999"), [], account_exists=False)
        assert result.verdict == "FAIL"
        assert "does not exist" in result.reasons[0]

    def test_a_quoted_reference_that_does_not_exist_fails(self):
        result = match(Claim(account_no=ACCOUNT, txn_ref="TXN-00000"), [txn()])
        assert result.verdict == "FAIL"
        assert "TXN-00000" in result.reasons[0]


class TestNoPlaintextAccountLeaves:
    """The verdict travels into event payloads and prompts, so it stays masked.

    Masking the structured field and then writing the number into a prose reason
    would defeat the point — the reasons are the part that gets rendered.
    """

    def test_a_pass_reason_masks_the_account(self):
        result = match(
            Claim(account_no=ACCOUNT, txn_ref="TXN-88213", amount_rm=2450.00), [txn()]
        )
        assert result.verdict == "PASS"
        assert ACCOUNT not in " ".join(result.reasons)
        assert "******6890" in result.reasons[0]

    def test_a_fail_reason_masks_the_account(self):
        for result in (
            match(Claim(account_no=ACCOUNT), [], account_exists=False),
            match(Claim(account_no=ACCOUNT, txn_ref="TXN-00000"), [txn()]),
        ):
            assert result.verdict == "FAIL"
            assert ACCOUNT not in " ".join(result.reasons)


class TestManualReview:
    """Core banking is silent or ambiguous. A person decides."""

    def test_no_candidate_goes_to_review(self):
        result = match(Claim(account_no=ACCOUNT, amount_rm=99.00), [txn()])
        assert result.verdict == "MANUAL_REVIEW"
        assert "No transaction" in result.reasons[0]

    def test_two_equally_good_candidates_go_to_review(self):
        """Picking one of two identical debits would be a guess dressed as a decision."""
        twins = [txn(txn_ref="TXN-1"), txn(txn_ref="TXN-2")]
        result = match(Claim(account_no=ACCOUNT, amount_rm=2450.00), twins)
        assert result.verdict == "MANUAL_REVIEW"
        assert "2 transactions match" in result.reasons[0]
        assert len(result.candidates) == 2

    def test_an_already_disputed_transaction_goes_to_review(self):
        result = match(
            Claim(account_no=ACCOUNT, txn_ref="TXN-88213", amount_rm=2450.00),
            [txn(is_disputed=True)],
        )
        assert result.verdict == "MANUAL_REVIEW"
        assert "already flagged as disputed" in result.reasons[-1]

    def test_missing_pack_required_evidence_goes_to_review(self):
        """A pack can demand evidence this claim cannot supply."""
        result = match(
            Claim(account_no=ACCOUNT, txn_ref="TXN-88213", amount_rm=2450.00),
            [txn()],
            required_evidence=["atm_journal_match"],
        )
        assert result.verdict == "MANUAL_REVIEW"
        assert "atm_journal_match" in result.reasons[-1]

    def test_a_stale_transaction_is_outside_the_window(self):
        old = txn(posted_at=(datetime.now(timezone.utc) - timedelta(days=400)).isoformat())
        result = match(Claim(account_no=ACCOUNT, amount_rm=2450.00), [old], window_days=120)
        assert result.verdict == "MANUAL_REVIEW"

    def test_credits_are_not_candidates_for_a_disputed_debit(self):
        credit = txn(direction="CREDIT")
        result = match(Claim(account_no=ACCOUNT, amount_rm=2450.00), [credit])
        assert result.verdict == "MANUAL_REVIEW"


class TestPass:
    """Exactly one row matches everything stated."""

    def test_reference_plus_amount_passes(self):
        result = match(
            Claim(account_no=ACCOUNT, txn_ref="TXN-88213", amount_rm=2450.00),
            [txn(), txn(txn_ref="TXN-OTHER", amount_rm=15.90)],
        )
        assert result.verdict == "PASS"
        assert result.matched["txn_ref"] == "TXN-88213"

    def test_amount_and_merchant_without_a_reference_passes(self):
        """Customers rarely quote a reference; the claim must still resolve."""
        result = match(
            Claim(account_no=ACCOUNT, amount_rm=2450.00, merchant="Techworld"),
            [txn(), txn(txn_ref="TXN-OTHER", amount_rm=15.90, merchant="GRAB")],
        )
        assert result.verdict == "PASS"
        assert result.matched["merchant"] == "TECHWORLD KL"

    def test_evidence_is_named_for_the_why_panel(self):
        result = match(
            Claim(account_no=ACCOUNT, txn_ref="TXN-88213", amount_rm=2450.00, merchant="Techworld"),
            [txn()],
        )
        assert "account_exists" in result.evidence
        assert "txn_ref_found" in result.evidence
        assert "amount_matches" in result.evidence
        assert "merchant_matches" in result.evidence

    def test_a_merchant_paraphrase_does_not_destroy_a_good_match(self):
        """Narrowing only applies when it helps — otherwise a typo costs a PASS."""
        result = match(
            Claim(account_no=ACCOUNT, txn_ref="TXN-88213", amount_rm=2450.00, merchant="Tekworld"),
            [txn()],
        )
        assert result.verdict == "PASS"

    def test_the_pack_tolerance_is_honoured(self):
        result = match(
            Claim(account_no=ACCOUNT, amount_rm=2455.00),
            [txn()],
            tolerance_pct=1.0,
        )
        assert result.verdict == "PASS"

    def test_a_verdict_always_carries_a_readable_reason(self):
        for claim in (
            Claim(account_no=ACCOUNT, txn_ref="TXN-88213", amount_rm=2450.00),
            Claim(account_no=ACCOUNT, amount_rm=1.00),
            Claim(account_no=ACCOUNT, txn_ref="TXN-NOPE"),
        ):
            assert match(claim, [txn()]).reasons
