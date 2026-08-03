"""Outbound compliance lint.

The case study's hard requirement is that a dissatisfied customer is told about the
Financial Markets Ombudsman Service. Most implementations discharge that by asking
the model nicely. This suite exists to show the difference: the clause is inserted by
control flow, its absence blocks the send, and neither outcome depends on what the
model happened to write.

Everything here is deterministic — no network, no model, no flakes.
"""

import pytest

from api.kernel.lint import (
    LintContext,
    fmos_applies,
    lint_or_raise,
    lint_outbound,
    render_fmos_block,
)
from api.kernel.rules import RulePack

COMPLIANT_BODY = """Dear Ms Nurul,

We acknowledge receipt of your complaint regarding a debit of RM 2,450.00 made to
your account on 14 March 2026.

Your case reference is CZ-2026-0412. We will complete our investigation and revert
to you by 21 March 2026.

If you have any questions in the meantime, please write to us at
complaints@mybank.com.my.

Yours sincerely,
MyBank Disputes Team
"""


def context(**overrides) -> LintContext:
    base = dict(
        case_ref="CZ-2026-0412",
        amount_rm=2450.00,
        outcome="REJECTED",
        due_date_display="21 March 2026",
    )
    base.update(overrides)
    return LintContext(**base)


def finding(report, rule_id):
    matches = [f for f in report.findings if f.rule_id == rule_id]
    assert matches, f"no finding for {rule_id}: got {[f.rule_id for f in report.findings]}"
    return matches[0]


class TestFmosApplicability:
    """When the customer's next step is outside the bank, they must be told."""

    @pytest.mark.parametrize(
        "outcome", ["REJECTED", "PARTIALLY_RESOLVED", "CUSTOMER_DISSATISFIED"]
    )
    def test_adverse_outcomes_trigger_the_clause(self, pack, outcome):
        assert fmos_applies(pack, context(outcome=outcome))

    @pytest.mark.parametrize("outcome", ["RESOLVED", "PENDING", "ACKNOWLEDGED"])
    def test_a_satisfied_customer_does_not_need_a_referral(self, pack, outcome):
        assert not fmos_applies(pack, context(outcome=outcome))

    def test_claims_above_the_scheme_ceiling_are_out_of_scope(self, pack):
        """FMOS jurisdiction stops at RM250,000; the letter must not imply otherwise."""
        assert not fmos_applies(pack, context(amount_rm=250_001))
        assert fmos_applies(pack, context(amount_rm=250_000))

    def test_an_unknown_amount_does_not_suppress_the_clause(self, pack):
        assert fmos_applies(pack, context(amount_rm=None))


class TestFmosRendering:
    def test_both_languages_are_rendered_for_a_bilingual_pack(self, pack):
        block = render_fmos_block(pack)
        assert "Financial Markets Ombudsman Service (FMOS)" in block
        assert "tidak berpuas hati" in block

    def test_a_monolingual_pack_gets_one_language(self, make_pack):
        pack = make_pack({"communication.languages": ["en"]})
        block = render_fmos_block(pack)
        assert "Financial Markets Ombudsman Service (FMOS)" in block
        assert "tidak berpuas hati" not in block


class TestFmosEnforcement:
    def test_a_missing_clause_is_inserted_rather_than_merely_reported(self, pack):
        report = lint_outbound(pack, COMPLIANT_BODY, context())

        assert finding(report, "FMOS_CLAUSE").status == "FIXED"
        assert report.repaired
        assert not report.blocked
        assert "Financial Markets Ombudsman Service (FMOS)" in report.body
        assert "six (6) months" in report.body

    def test_the_inserted_text_is_verbatim_from_the_rule_pack(self, pack):
        report = lint_outbound(pack, COMPLIANT_BODY, context())
        assert render_fmos_block(pack) in report.body

    def test_a_clause_the_model_already_wrote_is_left_alone(self, pack):
        drafted = COMPLIANT_BODY + (
            "\nShould our decision not satisfy you, you may escalate the matter to the "
            "Financial Markets Ombudsman Service within six months of this letter.\n"
        )
        report = lint_outbound(pack, drafted, context())

        assert finding(report, "FMOS_CLAUSE").status == "PASS"
        assert report.body == drafted
        assert not report.repaired

    def test_a_paraphrase_in_malay_also_counts(self, pack):
        drafted = COMPLIANT_BODY + (
            "\nAnda boleh merujuk perkara ini kepada FMOS dalam tempoh enam (6) bulan.\n"
        )
        assert finding(lint_outbound(pack, drafted, context()), "FMOS_CLAUSE").status == "PASS"

    def test_naming_the_scheme_without_the_window_is_not_enough(self, pack):
        """A referral right with no deadline is not a usable referral right."""
        drafted = COMPLIANT_BODY + "\nYou may refer this matter to FMOS.\n"
        assert finding(lint_outbound(pack, drafted, context()), "FMOS_CLAUSE").status == "FIXED"

    def test_no_clause_is_added_when_it_does_not_apply(self, pack):
        report = lint_outbound(pack, COMPLIANT_BODY, context(outcome="RESOLVED"))
        assert not any(f.rule_id == "FMOS_CLAUSE" for f in report.findings)
        assert report.body == COMPLIANT_BODY

    def test_linting_twice_does_not_insert_twice(self, pack):
        once = lint_outbound(pack, COMPLIANT_BODY, context())
        twice = lint_outbound(pack, once.body, context())
        assert twice.body == once.body
        assert finding(twice, "FMOS_CLAUSE").status == "PASS"

    def test_a_required_clause_with_no_text_blocks_the_send(self, pack):
        """Fail closed: a pack that cannot supply the wording must not silently skip it."""
        raw = {**pack.raw}
        raw["communication"] = {**raw["communication"]}
        raw["communication"]["fmos_clause"] = {
            k: v
            for k, v in raw["communication"]["fmos_clause"].items()
            if k not in ("text_en", "text_ms")
        }
        crippled = RulePack(category=pack.category, version=pack.version, raw=raw)

        report = lint_outbound(crippled, COMPLIANT_BODY, context())
        assert report.blocked
        assert finding(report, "FMOS_CLAUSE").status == "FAIL"


class TestMandatoryDisclosures:
    def test_a_complete_letter_passes_every_disclosure(self, pack):
        report = lint_outbound(pack, COMPLIANT_BODY, context())
        for rule_id in ("BNM_ACK", "BNM_CASE_REF", "BNM_TIMELINE", "CONTACT_CHANNEL"):
            assert finding(report, rule_id).ok

    def test_a_missing_acknowledgement_is_caught(self, pack):
        body = COMPLIANT_BODY.replace("We acknowledge receipt of your complaint", "Noted")
        report = lint_outbound(pack, body, context())
        assert report.blocked
        assert finding(report, "BNM_ACK").status == "FAIL"

    def test_a_missing_case_reference_is_caught(self, pack):
        body = COMPLIANT_BODY.replace("CZ-2026-0412", "your recent dispute")
        report = lint_outbound(pack, body, context())
        assert report.blocked
        assert "CZ-2026-0412" in finding(report, "BNM_CASE_REF").detail

    def test_a_duration_is_not_an_acceptable_deadline(self, pack):
        """'Within 5 working days' is not a date, and BNM expects a date."""
        body = COMPLIANT_BODY.replace("by 21 March 2026", "within five working days")
        report = lint_outbound(pack, body, context())
        assert report.blocked
        assert finding(report, "BNM_TIMELINE").status == "FAIL"

    def test_a_case_with_no_computed_deadline_cannot_be_sent(self, pack):
        report = lint_outbound(pack, COMPLIANT_BODY, context(due_date_display=None))
        assert report.blocked
        assert "no deadline was computed" in finding(report, "BNM_TIMELINE").detail

    def test_a_missing_contact_channel_is_caught(self, pack):
        body = COMPLIANT_BODY.replace("complaints@mybank.com.my", "our branch")
        report = lint_outbound(pack, body, context())
        assert report.blocked
        assert finding(report, "CONTACT_CHANNEL").status == "FAIL"

    def test_checks_are_insensitive_to_formatting(self, pack):
        """A date broken across a line wrap is still a date."""
        body = COMPLIANT_BODY.replace("by 21 March 2026", "by 21\n    March   2026")
        report = lint_outbound(pack, body, context())
        assert finding(report, "BNM_TIMELINE").ok

    def test_disclosures_are_checked_against_the_repaired_body(self, pack):
        """An inserted clause must be able to satisfy a downstream disclosure."""
        raw = {**pack.raw}
        raw["communication"] = {**raw["communication"]}
        raw["communication"]["mandatory_disclosures"] = list(
            raw["communication"]["mandatory_disclosures"]
        ) + [
            {
                "id": "FMOS_NAMED",
                "requirement": "Name the ombudsman scheme.",
                "text_contains": ["Financial Markets Ombudsman Service"],
            }
        ]
        pack_with_extra = RulePack(category=pack.category, version=pack.version, raw=raw)

        report = lint_outbound(pack_with_extra, COMPLIANT_BODY, context())
        assert finding(report, "FMOS_NAMED").status == "PASS"
        assert not report.blocked


class TestProhibitedPhrases:
    def test_an_over_promise_blocks_the_send(self, pack):
        body = COMPLIANT_BODY + "\nWe guarantee a full refund within 24 hours.\n"
        report = lint_outbound(pack, body, context())
        assert report.blocked
        assert finding(report, "PROHIBITED_PHRASE").status == "FAIL"

    def test_the_check_is_case_insensitive(self, pack):
        body = COMPLIANT_BODY + "\nThis is final and cannot be appealed.\n"
        assert lint_outbound(pack, body, context()).blocked

    def test_a_prohibited_phrase_is_never_repaired_away(self, pack):
        """Some drafts are wrong in a way that rewriting cannot fix."""
        body = COMPLIANT_BODY + "\nWe guarantee a full refund.\n"
        report = lint_outbound(pack, body, context())
        assert "We guarantee" in report.body
        assert report.blocked


class TestReport:
    def test_summary_counts_are_reported_for_the_lint_badge(self, pack):
        report = lint_outbound(pack, COMPLIANT_BODY, context())
        summary = report.summary()
        assert "passed" in summary
        assert "auto-inserted" in summary

    def test_a_blocked_report_names_the_failures(self, pack):
        report = lint_outbound(pack, COMPLIANT_BODY, context(due_date_display=None))
        assert len(report.failures) == 1
        assert not report.ok

    def test_lint_or_raise_returns_the_repaired_body_on_success(self, pack):
        body = lint_or_raise(pack, COMPLIANT_BODY, context())
        assert "Financial Markets Ombudsman Service (FMOS)" in body

    def test_lint_or_raise_refuses_a_blocked_draft(self, pack):
        with pytest.raises(ValueError, match="blocked by compliance lint"):
            lint_or_raise(pack, COMPLIANT_BODY + "\nWe guarantee it.\n", context())
