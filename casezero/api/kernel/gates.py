"""Authorisation gates. The place where "LLMs propose, the kernel disposes" is real.

No agent may move money or release a customer message. An agent produces a
*proposal*; this module decides, deterministically, whether that proposal executes,
goes to a human, or is refused outright.

Three invariants are enforced here and provable by test:

1. `FINANCIALLY_RESOLVED` is unreachable unless `verification_result == PASS`.
2. Confidence below the rule pack's floor routes to a human — a misclassification
   fails safe to a queue, never to a payout.
3. Above the dual-control threshold, one approver is not enough, and the second
   approver may not be the first.

Deterministic and LLM-free. Covered by api/tests/test_gates.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from api.kernel.lint import LintReport
from api.kernel.rules import RulePack

Action = Literal["POST", "MANUAL_REVIEW", "DENY"]

#: Legal state transitions. Anything absent is refused, so a bug cannot invent a
#: path from RECEIVED straight to FINANCIALLY_RESOLVED.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "RECEIVED": ("CLASSIFIED", "QUARANTINED"),
    "CLASSIFIED": ("VERIFIED", "REVIEW_PENDING", "QUARANTINED"),
    "VERIFIED": ("FINANCIALLY_RESOLVED", "REVIEW_PENDING", "QUARANTINED"),
    "REVIEW_PENDING": ("VERIFIED", "FINANCIALLY_RESOLVED", "COMMUNICATED", "QUARANTINED"),
    "FINANCIALLY_RESOLVED": ("COMMUNICATED",),
    "COMMUNICATED": ("CLOSED",),
    "CLOSED": (),
    "QUARANTINED": ("CLOSED",),
}

#: Reaching this status is a money movement, so it carries an extra precondition.
REQUIRES_PASS = "FINANCIALLY_RESOLVED"


@dataclass(frozen=True)
class GateDecision:
    """A ruling, with the reasons and the rule-pack keys that produced it.

    `citations` is what the "Why?" panel renders. A decision a customer or a
    regulator cannot trace back to a written rule is not defensible, so every
    ruling names its source.
    """

    action: Action
    requires_dual_control: bool = False
    reasons: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.action == "POST"

    @property
    def needs_human(self) -> bool:
        return self.action == "MANUAL_REVIEW"

    def explain(self) -> str:
        return " ".join(self.reasons)


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, ())


def assert_transition(
    current: str,
    target: str,
    *,
    verification_result: str | None = None,
) -> None:
    """Guard a status change. Raises ValueError on an illegal move.

    Called by the orchestrator before every write, which is what makes the state
    machine an actual constraint rather than a diagram in a document.
    """
    if not can_transition(current, target):
        allowed = TRANSITIONS.get(current, ())
        raise ValueError(
            f"Illegal transition {current} -> {target}. "
            f"Permitted from {current}: {allowed or '(terminal)'}"
        )

    if target == REQUIRES_PASS and verification_result != "PASS":
        raise ValueError(
            f"Refusing {current} -> {target}: verification_result is "
            f"{verification_result!r}, and money moves only on PASS."
        )


def authorize_resolution(
    pack: RulePack,
    *,
    verification_result: str | None,
    confidence: float | None,
    amount_rm: float | None,
    approved_by: str | None = None,
    dual_control_by: str | None = None,
) -> GateDecision:
    """Decide whether a financial resolution may be posted.

    Checks run cheapest-and-most-fundamental first, and the first blocking check
    wins, so the reported reason is the root cause rather than a downstream symptom.
    """
    reasons: list[str] = []
    citations: list[str] = []

    # 1. Did the classifier actually know what it was looking at?
    floor = pack.confidence_floor
    if confidence is None:
        return GateDecision(
            action="MANUAL_REVIEW",
            reasons=("No classification confidence was recorded, so the case cannot be "
                     "auto-resolved.",),
            citations=(f"{pack.category}.verification.confidence_floor = {floor}",),
        )
    if float(confidence) < floor:
        if not approved_by:
            return GateDecision(
                action="MANUAL_REVIEW",
                reasons=(
                    f"Classification confidence {float(confidence):.2f} is below the "
                    f"{floor:.2f} floor, so a human decides.",
                ),
                citations=(f"{pack.category}.verification.confidence_floor = {floor}",),
            )
        reasons.append(
            f"Classification confidence {float(confidence):.2f} is below the "
            f"{floor:.2f} floor; human investigator {approved_by} confirmed it."
        )
    else:
        reasons.append(f"Confidence {float(confidence):.2f} meets the {floor:.2f} floor.")
    citations.append(f"{pack.category}.verification.confidence_floor = {floor}")

    # 2. Did evidence from the core banking system support the claim?
    required = pack.requires_verification
    if verification_result == "FAIL":
        return GateDecision(
            action="DENY",
            reasons=("Verification returned FAIL: the core banking record does not "
                     "support the claim. No funds may move.",),
            citations=(f"{pack.category}.resolution.require_verification = {required}",),
        )
    if verification_result != required:
        return GateDecision(
            action="MANUAL_REVIEW",
            reasons=(
                f"Verification is {verification_result!r}, but {required!r} is required "
                f"before any financial resolution.",
            ),
            citations=(f"{pack.category}.resolution.require_verification = {required}",),
        )
    reasons.append("Verification returned PASS against the core banking record.")
    citations.append(f"{pack.category}.resolution.require_verification = {required}")

    # 3. Is the amount coherent?
    if amount_rm is None or float(amount_rm) <= 0:
        return GateDecision(
            action="MANUAL_REVIEW",
            reasons=(f"Disputed amount {amount_rm!r} is missing or not positive, so it "
                     f"cannot be posted.",),
            citations=(f"{pack.category}.resolution",),
        )
    amount = float(amount_rm)

    # 4. Thresholds.
    auto_max = pack.auto_approve_max_rm
    dual_above = pack.dual_control_above_rm

    if amount > dual_above:
        if not dual_control_by:
            return GateDecision(
                action="MANUAL_REVIEW",
                requires_dual_control=True,
                reasons=tuple(
                    reasons
                    + [
                        f"RM {amount:,.2f} exceeds the RM {dual_above:,.2f} dual-control "
                        f"threshold, so a second authoriser is required.",
                    ]
                ),
                citations=tuple(
                    citations
                    + [f"{pack.category}.resolution.dual_control_above_rm = {dual_above}"]
                ),
            )
        if approved_by and dual_control_by == approved_by:
            return GateDecision(
                action="DENY",
                requires_dual_control=True,
                reasons=(
                    "Dual control requires two different people; the same user cannot "
                    "be both approver and second authoriser.",
                ),
                citations=(
                    f"{pack.category}.resolution.dual_control_above_rm = {dual_above}",
                ),
            )
        reasons.append(
            f"RM {amount:,.2f} is above the dual-control threshold and carries a "
            f"distinct second authoriser."
        )
        citations.append(
            f"{pack.category}.resolution.dual_control_above_rm = {dual_above}"
        )
        return GateDecision(
            action="POST",
            requires_dual_control=True,
            reasons=tuple(reasons),
            citations=tuple(citations),
        )

    if amount > auto_max:
        if approved_by:
            reasons.append(
                f"RM {amount:,.2f} exceeds the RM {auto_max:,.2f} auto-approval "
                "ceiling and was approved by a human investigator."
            )
            citations.append(
                f"{pack.category}.resolution.auto_approve_max_rm = {auto_max}"
            )
            return GateDecision(
                action="POST", reasons=tuple(reasons), citations=tuple(citations)
            )
        return GateDecision(
            action="MANUAL_REVIEW",
            reasons=tuple(
                reasons
                + [
                    f"RM {amount:,.2f} exceeds the RM {auto_max:,.2f} auto-approval "
                    f"ceiling, so a human approves before posting.",
                ]
            ),
            citations=tuple(
                citations
                + [f"{pack.category}.resolution.auto_approve_max_rm = {auto_max}"]
            ),
        )

    reasons.append(
        f"RM {amount:,.2f} is within the RM {auto_max:,.2f} auto-approval ceiling."
    )
    citations.append(f"{pack.category}.resolution.auto_approve_max_rm = {auto_max}")
    return GateDecision(
        action="POST", reasons=tuple(reasons), citations=tuple(citations)
    )


def authorize_send(report: LintReport) -> GateDecision:
    """Release or withhold a customer message.

    The linter has already inserted whatever it could repair, so a blocked report
    here represents a requirement that genuinely cannot be met by rewriting.
    """
    if report.blocked:
        return GateDecision(
            action="DENY",
            reasons=tuple(f"{f.rule_id}: {f.detail}" for f in report.failures),
            citations=tuple(f.requirement for f in report.failures),
        )

    reasons = [f"Compliance lint passed ({report.summary()})."]
    if report.repaired:
        reasons.append(
            "Mandatory wording was inserted by the kernel rather than trusted to the "
            "model."
        )
    return GateDecision(
        action="POST",
        reasons=tuple(reasons),
        citations=tuple(f.requirement for f in report.findings if f.ok),
    )
