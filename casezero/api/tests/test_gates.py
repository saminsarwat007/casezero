"""Authorisation gates.

This is the suite a compliance officer would ask for. It is not testing that the
happy path works; it is testing that the unhappy paths cannot be walked:

* no route from a non-PASS verification to a posted journal entry,
* no auto-resolution below the confidence floor,
* no self-approval above the dual-control threshold,
* no customer message released while the lint report is blocked.

Every assertion below is a sentence we can say on stage and then prove.
"""

import pytest

from api.kernel.gates import (
    TRANSITIONS,
    GateDecision,
    assert_transition,
    authorize_resolution,
    authorize_send,
    can_transition,
)
from api.kernel.lint import LintContext, lint_outbound
from api.tests.test_lint import COMPLIANT_BODY


def resolve(pack, **overrides) -> GateDecision:
    """A clean, auto-approvable resolution unless a test says otherwise."""
    kwargs = dict(verification_result="PASS", confidence=0.94, amount_rm=2450.00)
    kwargs.update(overrides)
    return authorize_resolution(pack, **kwargs)


class TestStateMachine:
    @pytest.mark.parametrize(
        "current,target",
        [
            ("RECEIVED", "CLASSIFIED"),
            ("CLASSIFIED", "VERIFIED"),
            ("VERIFIED", "FINANCIALLY_RESOLVED"),
            ("FINANCIALLY_RESOLVED", "COMMUNICATED"),
            ("COMMUNICATED", "CLOSED"),
            ("CLASSIFIED", "REVIEW_PENDING"),
            ("REVIEW_PENDING", "FINANCIALLY_RESOLVED"),
        ],
    )
    def test_the_intended_path_is_permitted(self, current, target):
        assert can_transition(current, target)

    @pytest.mark.parametrize(
        "current,target",
        [
            ("RECEIVED", "FINANCIALLY_RESOLVED"),  # skipping classification entirely
            ("RECEIVED", "CLOSED"),
            ("CLASSIFIED", "FINANCIALLY_RESOLVED"),  # skipping verification
            ("CLOSED", "RECEIVED"),  # reopening a closed case by rewriting status
            ("FINANCIALLY_RESOLVED", "VERIFIED"),  # unwinding a posted entry
            ("QUARANTINED", "CLASSIFIED"),  # letting a quarantined email back in
        ],
    )
    def test_shortcuts_are_refused(self, current, target):
        assert not can_transition(current, target)
        with pytest.raises(ValueError, match="Illegal transition"):
            assert_transition(current, target, verification_result="PASS")

    def test_every_state_is_reachable_and_declared(self):
        declared = set(TRANSITIONS)
        for targets in TRANSITIONS.values():
            assert set(targets) <= declared

    def test_closed_is_terminal(self):
        assert TRANSITIONS["CLOSED"] == ()

    def test_quarantine_is_reachable_from_every_live_state(self):
        """An injection can be discovered at any point before the case closes."""
        for state in ("RECEIVED", "CLASSIFIED", "VERIFIED", "REVIEW_PENDING"):
            assert "QUARANTINED" in TRANSITIONS[state]

    def test_money_moves_only_on_pass(self):
        assert_transition("VERIFIED", "FINANCIALLY_RESOLVED", verification_result="PASS")
        for result in ("FAIL", "MANUAL_REVIEW", None, "pass"):
            with pytest.raises(ValueError, match="money moves only on PASS"):
                assert_transition(
                    "VERIFIED", "FINANCIALLY_RESOLVED", verification_result=result
                )

    def test_the_pass_requirement_survives_the_review_route(self):
        """A human approval does not substitute for evidence."""
        with pytest.raises(ValueError, match="money moves only on PASS"):
            assert_transition(
                "REVIEW_PENDING", "FINANCIALLY_RESOLVED", verification_result="FAIL"
            )


class TestConfidenceFloor:
    def test_a_confident_classification_proceeds(self, pack):
        assert resolve(pack, confidence=0.94).action == "POST"

    def test_the_floor_is_inclusive(self, pack):
        assert resolve(pack, confidence=pack.confidence_floor).action == "POST"

    def test_an_unsure_classification_goes_to_a_human(self, pack):
        decision = resolve(pack, confidence=0.62)
        assert decision.action == "MANUAL_REVIEW"
        assert decision.needs_human
        assert "0.62" in decision.explain()

    def test_a_human_can_confirm_an_unsure_classification(self, pack):
        decision = resolve(
            pack,
            confidence=0.62,
            approved_by="user:investigator1",
        )
        assert decision.action == "POST"
        assert "confirmed it" in decision.explain()

    def test_a_missing_confidence_goes_to_a_human(self, pack):
        assert resolve(pack, confidence=None).action == "MANUAL_REVIEW"

    def test_the_floor_is_cited_not_hardcoded(self, pack):
        decision = resolve(pack, confidence=0.10)
        assert any("confidence_floor" in c for c in decision.citations)

    def test_confidence_is_checked_before_anything_else(self, pack):
        """The reported reason should be the root cause, not a later symptom."""
        decision = resolve(pack, confidence=0.10, verification_result="FAIL", amount_rm=None)
        assert "confidence" in decision.explain().lower()


class TestVerificationRequirement:
    def test_a_failed_verification_is_denied_outright(self, pack):
        """FAIL means the core banking record contradicts the claim — not a queue item."""
        decision = resolve(pack, verification_result="FAIL")
        assert decision.action == "DENY"
        assert not decision.allowed
        assert not decision.needs_human

    @pytest.mark.parametrize("result", ["MANUAL_REVIEW", "PENDING", None])
    def test_anything_short_of_pass_goes_to_a_human(self, pack, result):
        decision = resolve(pack, verification_result=result)
        assert decision.action == "MANUAL_REVIEW"

    def test_no_amount_of_confidence_substitutes_for_evidence(self, pack):
        assert resolve(pack, confidence=1.0, verification_result="FAIL").action == "DENY"


class TestAmountSanity:
    @pytest.mark.parametrize("amount", [None, 0, -50.0])
    def test_an_incoherent_amount_cannot_be_posted(self, pack, amount):
        assert resolve(pack, amount_rm=amount).action == "MANUAL_REVIEW"


class TestThresholds:
    def test_a_small_verified_claim_auto_resolves(self, pack):
        decision = resolve(pack, amount_rm=2450.00)
        assert decision.action == "POST"
        assert not decision.requires_dual_control

    def test_the_auto_approval_ceiling_is_inclusive(self, pack):
        assert resolve(pack, amount_rm=pack.auto_approve_max_rm).action == "POST"

    def test_a_claim_above_the_ceiling_waits_for_a_human(self, make_pack):
        """A pack may sit a review band between auto-approval and dual control."""
        pack = make_pack(
            {
                "resolution.auto_approve_max_rm": 1000,
                "resolution.dual_control_above_rm": 5000,
            }
        )
        decision = resolve(pack, amount_rm=2450.00)
        assert decision.action == "MANUAL_REVIEW"
        assert not decision.requires_dual_control
        assert any("auto_approve_max_rm" in c for c in decision.citations)

    def test_a_human_can_approve_the_review_band(self, make_pack):
        pack = make_pack(
            {
                "resolution.auto_approve_max_rm": 1000,
                "resolution.dual_control_above_rm": 5000,
            }
        )
        decision = resolve(
            pack,
            amount_rm=2450.00,
            approved_by="user:investigator1",
        )
        assert decision.action == "POST"
        assert not decision.requires_dual_control
        assert "approved by a human investigator" in decision.explain()

    def test_a_large_claim_demands_a_second_authoriser(self, pack):
        decision = resolve(pack, amount_rm=8200.00, approved_by="user:ops1")
        assert decision.action == "MANUAL_REVIEW"
        assert decision.requires_dual_control
        assert "second authoriser" in decision.explain()

    def test_a_large_claim_posts_once_two_people_have_signed(self, pack):
        decision = resolve(
            pack,
            amount_rm=8200.00,
            approved_by="user:ops1",
            dual_control_by="user:manager2",
        )
        assert decision.action == "POST"
        assert decision.requires_dual_control

    def test_self_approval_is_refused(self, pack):
        """The classic control failure: one person clicking approve twice."""
        decision = resolve(
            pack,
            amount_rm=8200.00,
            approved_by="user:ops1",
            dual_control_by="user:ops1",
        )
        assert decision.action == "DENY"
        assert "two different people" in decision.explain()

    def test_the_threshold_is_exclusive(self, pack):
        """Exactly at the threshold is not above it."""
        at = resolve(pack, amount_rm=pack.dual_control_above_rm)
        above = resolve(pack, amount_rm=pack.dual_control_above_rm + 0.01)
        assert at.action == "POST"
        assert not at.requires_dual_control
        assert above.requires_dual_control


class TestExplainability:
    def test_a_posted_decision_cites_every_rule_it_relied_on(self, pack):
        decision = resolve(pack)
        assert decision.action == "POST"
        joined = " ".join(decision.citations)
        assert "confidence_floor" in joined
        assert "require_verification" in joined
        assert "auto_approve_max_rm" in joined

    def test_citations_name_the_category_so_the_why_panel_can_link_to_the_pack(self, pack):
        for citation in resolve(pack).citations:
            assert citation.startswith(pack.category + ".")

    def test_every_decision_can_be_read_aloud(self, pack):
        for decision in (
            resolve(pack),
            resolve(pack, confidence=0.1),
            resolve(pack, verification_result="FAIL"),
            resolve(pack, amount_rm=99999.0),
        ):
            assert decision.reasons
            assert decision.explain().strip()


class TestSendGate:
    def test_a_clean_draft_is_released(self, pack):
        report = lint_outbound(
            pack,
            COMPLIANT_BODY,
            LintContext(
                case_ref="CZ-2026-0412",
                amount_rm=2450.00,
                outcome="REJECTED",
                due_date_display="21 March 2026",
            ),
        )
        decision = authorize_send(report)
        assert decision.action == "POST"
        assert "inserted by the kernel" in decision.explain()

    def test_a_blocked_report_withholds_the_message(self, pack):
        report = lint_outbound(
            pack,
            COMPLIANT_BODY + "\nWe guarantee a refund.\n",
            LintContext(
                case_ref="CZ-2026-0412",
                amount_rm=2450.00,
                outcome="REJECTED",
                due_date_display="21 March 2026",
            ),
        )
        decision = authorize_send(report)
        assert decision.action == "DENY"
        assert "PROHIBITED_PHRASE" in decision.explain()

    def test_the_refusal_names_the_requirement_the_draft_missed(self, pack):
        report = lint_outbound(
            pack,
            COMPLIANT_BODY,
            LintContext(case_ref="CZ-2026-0412", outcome="REJECTED", due_date_display=None),
        )
        decision = authorize_send(report)
        assert decision.action == "DENY"
        assert any("deadline" in c.lower() for c in decision.citations)
