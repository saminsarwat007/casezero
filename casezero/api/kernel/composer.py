"""Governed natural-language policy changes.

The model has one narrow job: translate an operator's sentence into typed edits.
It never writes YAML directly and it never decides whether an edit is allowed.
This module applies the edits to a copy of the active pack, rejects protected or
unknown paths, validates the whole candidate, and simulates the operational
impact before anything can be persisted or activated.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any, Iterable, Mapping

import yaml
from deepdiff import DeepDiff
from pydantic import BaseModel, Field, field_validator

from api.agents.firewall import scan
from api.kernel.rules import RulePack, RulePackError, load_yaml, path_is_immutable


class ComposerError(ValueError):
    """A proposal is unsafe, malformed, or cannot be simulated."""


# Small on purpose. A model cannot create a field simply because it looks
# plausible. Extending this list is a reviewed code change with tests.
EDITABLE_PATHS: frozenset[str] = frozenset(
    {
        "resolution.auto_approve_max_rm",
        "resolution.dual_control_above_rm",
        "verification.amount_tolerance_pct",
        "sla.breach_forecast_threshold",
        "communication.prohibited_phrases",
        "workflow.notify_roles",
    }
)

NOTIFY_ROLES = frozenset({"OPS", "INVESTIGATOR", "COMPLIANCE", "ADMIN", "BRANCH_MANAGER"})


class PolicyEdit(BaseModel):
    path: str
    value: Any
    reason: str = ""

    @field_validator("path")
    @classmethod
    def normalise_path(cls, value: str) -> str:
        return value.strip().removeprefix("root.")


class PolicyIntent(BaseModel):
    target_category: str
    summary: str
    edits: list[PolicyEdit] = Field(min_length=1, max_length=8)


@dataclass(frozen=True)
class PolicyImpact:
    corpus_cases: int
    eligible_before: int
    eligible_after: int
    auto_resolution_rate_before: float
    auto_resolution_rate_after: float
    exposure_rm_before: float
    exposure_rm_after: float
    sla_breach_risk_before: float
    sla_breach_risk_after: float
    changed_case_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "corpus_cases": self.corpus_cases,
            "eligible_before": self.eligible_before,
            "eligible_after": self.eligible_after,
            "auto_resolution_rate_before": self.auto_resolution_rate_before,
            "auto_resolution_rate_after": self.auto_resolution_rate_after,
            "exposure_rm_before": self.exposure_rm_before,
            "exposure_rm_after": self.exposure_rm_after,
            "sla_breach_risk_before": self.sla_breach_risk_before,
            "sla_breach_risk_after": self.sla_breach_risk_after,
            "changed_case_refs": list(self.changed_case_refs),
        }


@dataclass(frozen=True)
class PolicyCandidate:
    pack: RulePack
    intent: PolicyIntent
    diff: dict[str, Any]
    plain_english_diff: str
    impact: PolicyImpact
    risk_flag: str | None


SYSTEM_PROMPT = """You translate one bank-operations policy request into typed edits.
Return only the requested PolicyIntent schema. You may use ONLY these paths:
- resolution.auto_approve_max_rm (non-negative number)
- resolution.dual_control_above_rm (non-negative number)
- verification.amount_tolerance_pct (0..100)
- sla.breach_forecast_threshold (0.05..0.80)
- communication.prohibited_phrases (complete list of strings)
- workflow.notify_roles (complete list from OPS, INVESTIGATOR, COMPLIANCE, ADMIN,
  BRANCH_MANAGER)
Do not emit category, version, SLA working days, confidence floor, fallback,
require_verification, mandatory disclosures, FMOS, or audit edits. If the request
mentions a threshold such as 'under RM500', encode 500 as the ceiling. Do not
invent extra fields. The target category is supplied by the application."""


def _get_path(raw: Mapping[str, Any], path: str) -> Any:
    current: Any = raw
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return None
        current = current[segment]
    return current


def _set_path(raw: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = raw
    for segment in parts[:-1]:
        child = current.setdefault(segment, {})
        if not isinstance(child, dict):
            raise ComposerError(f"Cannot edit {path!r}: {segment!r} is not a mapping.")
        current = child
    current[parts[-1]] = deepcopy(value)


def _validate_edit(edit: PolicyEdit) -> None:
    if path_is_immutable(edit.path):
        raise ComposerError(f"Protected policy path cannot be changed: {edit.path}")
    if edit.path not in EDITABLE_PATHS:
        raise ComposerError(f"Unknown or non-editable policy path: {edit.path}")

    value = edit.value
    if edit.path in {
        "resolution.auto_approve_max_rm",
        "resolution.dual_control_above_rm",
    }:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ComposerError(f"{edit.path} must be a non-negative number.")
    elif edit.path == "verification.amount_tolerance_pct":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ComposerError("verification.amount_tolerance_pct must be between 0 and 100.")
    elif edit.path == "sla.breach_forecast_threshold":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.05 <= value <= 0.8:
            raise ComposerError("sla.breach_forecast_threshold must be between 0.05 and 0.80.")
    elif edit.path == "communication.prohibited_phrases":
        if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
            raise ComposerError("communication.prohibited_phrases must be a non-empty string list.")
    elif edit.path == "workflow.notify_roles":
        if not isinstance(value, list) or any(str(v) not in NOTIFY_ROLES for v in value):
            raise ComposerError(f"workflow.notify_roles may contain only {sorted(NOTIFY_ROLES)}.")


def apply_intent(base: RulePack, intent: PolicyIntent) -> RulePack:
    """Return a validated, version-bumped candidate or fail closed."""
    if intent.target_category != base.category:
        raise ComposerError(
            f"Intent targets {intent.target_category!r}; active pack is {base.category!r}."
        )
    raw = deepcopy(base.raw)
    seen: set[str] = set()
    for edit in intent.edits:
        if edit.path in seen:
            raise ComposerError(f"Duplicate edit path: {edit.path}")
        seen.add(edit.path)
        _validate_edit(edit)
        _set_path(raw, edit.path, edit.value)

    auto = float(raw.get("resolution", {}).get("auto_approve_max_rm", 0))
    dual = float(raw.get("resolution", {}).get("dual_control_above_rm", 0))
    if dual and auto > dual:
        raise ComposerError(
            "auto_approve_max_rm cannot exceed dual_control_above_rm; that would "
            "silently skip the second approver."
        )

    raw["version"] = base.version + 1
    try:
        return load_yaml(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    except RulePackError as exc:
        raise ComposerError(f"Candidate failed rule-pack validation: {exc}") from exc


def _deep_diff(base: RulePack, candidate: RulePack) -> dict[str, Any]:
    # Version is system-managed; the operator diff should describe policy, not
    # bookkeeping. DeepDiff is still the canonical machine diff persisted in DB.
    left = deepcopy(base.raw)
    right = deepcopy(candidate.raw)
    left.pop("version", None)
    right.pop("version", None)
    return json.loads(
        DeepDiff(left, right, ignore_order=False, verbose_level=2).to_json()
    )


def _plain_diff(base: RulePack, intent: PolicyIntent) -> str:
    lines: list[str] = []
    for edit in intent.edits:
        before = _get_path(base.raw, edit.path)
        lines.append(f"{edit.path}: {before!r} → {edit.value!r}")
    return "\n".join(lines)


def _eligible(case: Mapping[str, Any], pack: RulePack) -> bool:
    if case.get("category") != pack.category:
        return False
    if case.get("verification_result", "PASS") != "PASS":
        return False
    confidence = float(case.get("confidence", 1.0))
    amount = float(case.get("amount_rm") or 0)
    return confidence >= pack.confidence_floor and 0 < amount <= pack.auto_approve_max_rm


def simulate(
    base: RulePack,
    candidate: RulePack,
    corpus: Iterable[Mapping[str, Any]],
) -> PolicyImpact:
    rows = list(corpus)
    relevant = [row for row in rows if row.get("category") == base.category]
    before = [row for row in relevant if _eligible(row, base)]
    after = [row for row in relevant if _eligible(row, candidate)]
    changed = [
        str(row.get("case_ref") or row.get("id") or "UNLABELLED")
        for row in relevant
        if _eligible(row, base) != _eligible(row, candidate)
    ]

    def rate(items: list[Mapping[str, Any]]) -> float:
        return round(len(items) / len(relevant), 4) if relevant else 0.0

    # SLA days are immutable. Raising the forecast threshold is operationally
    # safer (earlier escalation), so only lowering it increases projected risk.
    before_threshold = base.breach_forecast_threshold
    after_threshold = candidate.breach_forecast_threshold
    before_risk = round(max(0.0, 1.0 - before_threshold), 4)
    after_risk = round(max(0.0, 1.0 - after_threshold), 4)
    return PolicyImpact(
        corpus_cases=len(relevant),
        eligible_before=len(before),
        eligible_after=len(after),
        auto_resolution_rate_before=rate(before),
        auto_resolution_rate_after=rate(after),
        exposure_rm_before=round(sum(float(row.get("amount_rm") or 0) for row in before), 2),
        exposure_rm_after=round(sum(float(row.get("amount_rm") or 0) for row in after), 2),
        sla_breach_risk_before=before_risk,
        sla_breach_risk_after=after_risk,
        changed_case_refs=tuple(changed),
    )


def candidate_from_intent(
    base: RulePack,
    intent: PolicyIntent,
    corpus: Iterable[Mapping[str, Any]],
) -> PolicyCandidate:
    candidate = apply_intent(base, intent)
    impact = simulate(base, candidate, corpus)
    risk = (
        "RAISES_SLA_BREACH_RISK"
        if impact.sla_breach_risk_after > impact.sla_breach_risk_before
        else None
    )
    return PolicyCandidate(
        pack=candidate,
        intent=intent,
        diff=_deep_diff(base, candidate),
        plain_english_diff=_plain_diff(base, intent),
        impact=impact,
        risk_flag=risk,
    )


async def interpret_request(
    request: str,
    category: str,
    ctx: Any,
) -> PolicyIntent:
    """Use the model only for language mapping; every control follows in code."""
    verdict = scan(request)
    if verdict.hostile:
        raise ComposerError(f"Policy request blocked by the injection firewall: {verdict.reason()}")
    result = await ctx.complete(
        "composer",
        f"Target category: {category}\nOperator request: {verdict.cleaned}",
        system=SYSTEM_PROMPT,
        schema=PolicyIntent,
        temperature=0.0,
    )
    try:
        intent = PolicyIntent.model_validate(result.require_data())
    except Exception as exc:  # noqa: BLE001 - normalise provider/schema failures
        raise ComposerError(f"The model did not return a valid policy intent: {exc}") from exc
    if intent.target_category != category:
        raise ComposerError("The model changed the target category; proposal refused.")
    return intent
