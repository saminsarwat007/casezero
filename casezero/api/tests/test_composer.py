"""Policy Composer: a model may propose, but protected policy never moves."""

from __future__ import annotations

import pytest

from api.kernel.composer import (
    ComposerError,
    PolicyEdit,
    PolicyIntent,
    apply_intent,
    candidate_from_intent,
)
from api.kernel.rules import RulePack


def intent(pack: RulePack, *edits: PolicyEdit) -> PolicyIntent:
    return PolicyIntent(
        target_category=pack.category,
        summary="Operator-requested threshold change.",
        edits=list(edits),
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("communication.fmos_clause.window_months", 12),
        ("communication.mandatory_disclosures", []),
        ("audit.hash_chain", "disabled"),
        ("resolution.require_verification", "MANUAL_REVIEW"),
        ("verification.confidence_floor", 0.0),
        ("sla.High.working_days", 90),
    ],
)
def test_protected_paths_are_refused(pack, path, value) -> None:
    with pytest.raises(ComposerError, match="Protected policy path"):
        apply_intent(pack, intent(pack, PolicyEdit(path=path, value=value)))


def test_model_cannot_invent_a_plausible_field(pack) -> None:
    with pytest.raises(ComposerError, match="Unknown or non-editable"):
        apply_intent(
            pack,
            intent(pack, PolicyEdit(path="resolution.skip_human_review", value=True)),
        )


def test_safe_threshold_change_is_versioned(pack) -> None:
    candidate = apply_intent(
        pack,
        intent(
            pack,
            PolicyEdit(path="resolution.auto_approve_max_rm", value=2500),
            PolicyEdit(path="workflow.notify_roles", value=["BRANCH_MANAGER"]),
        ),
    )
    assert candidate.version == pack.version + 1
    assert candidate.auto_approve_max_rm == 2500
    assert candidate.raw["workflow"]["notify_roles"] == ["BRANCH_MANAGER"]
    assert candidate.raw["communication"]["fmos_clause"] == pack.raw["communication"]["fmos_clause"]


def test_auto_ceiling_cannot_jump_past_dual_control(pack) -> None:
    with pytest.raises(ComposerError, match="cannot exceed dual_control"):
        apply_intent(
            pack,
            intent(pack, PolicyEdit(path="resolution.auto_approve_max_rm", value=9000)),
        )


def test_simulation_names_every_case_whose_outcome_changes(pack) -> None:
    corpus = [
        {
            "case_ref": "EV-001",
            "category": pack.category,
            "amount_rm": 2400,
            "confidence": 0.95,
            "verification_result": "PASS",
        },
        {
            "case_ref": "EV-002",
            "category": pack.category,
            "amount_rm": 2800,
            "confidence": 0.95,
            "verification_result": "PASS",
        },
        {
            "case_ref": "EV-003",
            "category": "billing_error",
            "amount_rm": 100,
            "confidence": 0.95,
            "verification_result": "PASS",
        },
    ]
    proposal = candidate_from_intent(
        pack,
        intent(pack, PolicyEdit(path="resolution.auto_approve_max_rm", value=2500)),
        corpus,
    )
    assert proposal.impact.eligible_before == 2
    assert proposal.impact.eligible_after == 1
    assert proposal.impact.changed_case_refs == ("EV-002",)
    assert "resolution.auto_approve_max_rm" in proposal.plain_english_diff
    assert proposal.diff


def test_lowering_breach_forecast_threshold_is_flagged(pack) -> None:
    proposal = candidate_from_intent(
        pack,
        intent(pack, PolicyEdit(path="sla.breach_forecast_threshold", value=0.10)),
        [],
    )
    assert proposal.risk_flag == "RAISES_SLA_BREACH_RISK"


def test_duplicate_paths_are_refused(pack) -> None:
    with pytest.raises(ComposerError, match="Duplicate edit path"):
        apply_intent(
            pack,
            intent(
                pack,
                PolicyEdit(path="resolution.auto_approve_max_rm", value=100),
                PolicyEdit(path="resolution.auto_approve_max_rm", value=200),
            ),
        )
