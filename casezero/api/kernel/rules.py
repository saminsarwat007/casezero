"""Rule packs: policy as code, loaded and validated.

A rule pack is the only place a category's behaviour is defined. Adding categories
two through seven is therefore configuration, not code — which is what makes the
claim "the kernel scales to all seven" checkable rather than aspirational.

Two things live here and nowhere else:

* **The immutability contract.** Some keys exist to protect the customer and the
  regulator, so the Policy Composer is forbidden from touching them no matter how
  an operator phrases the request. Enumerating them here means the restriction is
  a property of the system rather than a hope about prompt behaviour.
* **The condition evaluator.** Urgency assignment must be deterministic and
  explainable, so it is a tiny predicate language rather than a model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

RULE_PACKS_DIR = Path(__file__).resolve().parent.parent.parent / "rule_packs"

CATEGORIES = (
    "unauthorized_transaction",
    "billing_error",
    "mis_selling",
    "atm_debit_card",
    "insurance_takaful",
    "loan_financing",
    "emoney_digital",
)

URGENCIES = ("High", "Medium", "Low")

#: Mirrors the `case_outcome` enum in 001_init.sql. A pack that names an outcome
#: the database cannot produce declares a rule that never fires — the same silent
#: failure as a mistyped check, so it is rejected at load.
OUTCOMES = (
    "RESOLVED_IN_FULL",
    "PARTIALLY_RESOLVED",
    "REJECTED",
    "CUSTOMER_DISSATISFIED",
    "PENDING",
)

# ─── The immutability contract ───────────────────────────────────────────────
# `*` matches exactly one path segment. A path listed here also protects
# everything beneath it.
#
# These are not arbitrary. Each one is the difference between a policy change and
# a compliance breach:
#   sla.*.working_days        - BNM sets these, not the bank
#   verification.*            - an unsure classification must never auto-resolve
#   resolution.require_*      - money never moves without a PASS
#   communication.fmos_clause - the customer's route to the ombudsman
#   audit                     - the tamper-evidence itself
IMMUTABLE_PATHS: tuple[str, ...] = (
    "category",
    "version",
    "sla.*.working_days",
    "verification.confidence_floor",
    "verification.fallback_on_ambiguity",
    "resolution.require_verification",
    "communication.fmos_clause",
    "communication.mandatory_disclosures",
    "audit",
)

#: Lists that may grow but never shrink. Removing a disclosure is a breach even
#: though adding one is harmless, so equality is the wrong test for them.
APPEND_ONLY_PATHS: tuple[str, ...] = ("communication.mandatory_disclosures",)

# ─── The disclosure contract ────────────────────────────────────────────────
# Every check a pack may ask for, enumerated. `api/kernel/lint.py` implements
# exactly this set.
#
# The enumeration is the point. A pack that asked for `must_state_amount_rm` — one
# character off — would otherwise produce a disclosure the linter does not know how
# to check, and an unchecked disclosure reports PASS. A compliance rule that always
# passes is worse than no rule, so a typo is a load-time error instead.
DISCLOSURE_CHECKS: frozenset[str] = frozenset(
    {
        "text_contains",
        "must_include_case_ref",
        "must_state_deadline_date",
        "must_state_amount",
    }
)

#: Metadata a disclosure may carry alongside its checks.
DISCLOSURE_KEYS: frozenset[str] = DISCLOSURE_CHECKS | {
    "id",
    "requirement",
    "note",
    "applies_when_outcome_in",
}


class RulePackError(ValueError):
    """Raised when a pack is malformed. Never swallowed — a bad pack must not run."""


def path_is_immutable(dotted: str) -> bool:
    """True if `dotted`, or any ancestor of it, is protected."""
    segments = dotted.split(".")
    for pattern in IMMUTABLE_PATHS:
        expected = pattern.split(".")
        if len(expected) > len(segments):
            continue
        if all(e == "*" or e == a for e, a in zip(expected, segments)):
            return True
    return False


def path_is_append_only(dotted: str) -> bool:
    return any(
        dotted == pattern or dotted.startswith(pattern + ".")
        for pattern in APPEND_ONLY_PATHS
    )


# ─── Condition evaluator ────────────────────────────────────────────────────

def _compare(operator: str, actual: Any, expected: Any) -> bool:
    if actual is None:
        # A missing fact cannot satisfy a condition. Failing closed here is what
        # sends an incomplete case to a human instead of guessing.
        return False
    try:
        if operator == "equals":
            return str(actual).lower() == str(expected).lower()
        if operator == "not_equals":
            return str(actual).lower() != str(expected).lower()
        if operator == "gte":
            return float(actual) >= float(expected)
        if operator == "lte":
            return float(actual) <= float(expected)
        if operator == "gt":
            return float(actual) > float(expected)
        if operator == "lt":
            return float(actual) < float(expected)
        if operator == "in":
            return str(actual).lower() in [str(v).lower() for v in expected]
        if operator == "contains":
            if isinstance(actual, (list, tuple, set)):
                return any(str(expected).lower() == str(v).lower() for v in actual)
            return str(expected).lower() in str(actual).lower()
    except (TypeError, ValueError):
        return False
    raise RulePackError(f"Unknown operator {operator!r}")


def evaluate_condition(condition: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    """All clauses must hold (AND). Empty condition matches nothing, not everything."""
    if not condition:
        return False
    for field, test in condition.items():
        if not isinstance(test, Mapping):
            raise RulePackError(
                f"Condition on {field!r} must be a mapping like {{gte: 500}}, got {test!r}"
            )
        for operator, expected in test.items():
            if not _compare(operator, facts.get(field), expected):
                return False
    return True


@dataclass(frozen=True)
class UrgencyDecision:
    """Urgency plus the reason, because every decision must be explainable."""

    urgency: str
    because: str
    rule_index: int | None


# ─── The pack ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RulePack:
    """A validated pack. Typed accessors keep YAML shape out of the kernel."""

    category: str
    version: int
    raw: dict[str, Any]
    source_yaml: str = ""

    # ─── SLA ────────────────────────────────────────────────────────────────

    def sla_working_days(self, urgency: str) -> int:
        block = self.raw.get("sla", {}).get(urgency)
        if not block or "working_days" not in block:
            raise RulePackError(
                f"{self.category} v{self.version}: no SLA defined for urgency {urgency!r}"
            )
        return int(block["working_days"])

    @property
    def breach_forecast_threshold(self) -> float:
        return float(self.raw.get("sla", {}).get("breach_forecast_threshold", 0.20))

    # ─── Urgency ────────────────────────────────────────────────────────────

    def assign_urgency(self, facts: Mapping[str, Any]) -> UrgencyDecision:
        """First matching rule wins; a `default` entry terminates the list.

        Order is meaningful and intentional: the vulnerable-customer rule sits
        above the amount thresholds so a RM90 dispute from an assisted-banking
        customer outranks a RM4,000 one.
        """
        rules = self.raw.get("urgency_rules") or []
        for index, rule in enumerate(rules):
            if "default" in rule:
                return UrgencyDecision(
                    urgency=str(rule["default"]),
                    because="No specific rule matched; category default applied.",
                    rule_index=index,
                )
            if evaluate_condition(rule.get("when", {}), facts):
                return UrgencyDecision(
                    urgency=str(rule["then"]),
                    because=str(rule.get("because") or _describe(rule.get("when", {}))),
                    rule_index=index,
                )
        return UrgencyDecision(
            urgency="Medium",
            because="No urgency rules matched and no default was defined; "
                    "defaulting to Medium so the case is never left unbounded.",
            rule_index=None,
        )

    # ─── Verification ───────────────────────────────────────────────────────

    @property
    def confidence_floor(self) -> float:
        return float(self.raw.get("verification", {}).get("confidence_floor", 0.75))

    @property
    def required_evidence(self) -> tuple[str, ...]:
        return tuple(self.raw.get("verification", {}).get("required_evidence", ()))

    @property
    def amount_tolerance_pct(self) -> float:
        return float(self.raw.get("verification", {}).get("amount_tolerance_pct", 1.0))

    @property
    def fallback_on_ambiguity(self) -> str:
        return str(
            self.raw.get("verification", {}).get("fallback_on_ambiguity", "MANUAL_REVIEW")
        )

    # ─── Resolution ─────────────────────────────────────────────────────────

    @property
    def journal_type(self) -> str:
        return str(self.raw.get("resolution", {}).get("journal_type", "CREDIT_ADJUSTMENT"))

    @property
    def debit_account(self) -> str:
        return str(
            self.raw.get("resolution", {}).get("debit_account", "GL-1499-DISPUTE-SUSPENSE")
        )

    @property
    def requires_verification(self) -> str:
        return str(self.raw.get("resolution", {}).get("require_verification", "PASS"))

    @property
    def auto_approve_max_rm(self) -> float:
        return float(self.raw.get("resolution", {}).get("auto_approve_max_rm", 0.0))

    @property
    def dual_control_above_rm(self) -> float:
        return float(self.raw.get("resolution", {}).get("dual_control_above_rm", 0.0))

    @property
    def narrative_template(self) -> str:
        return str(
            self.raw.get("resolution", {}).get(
                "narrative_template", "Adjustment for dispute {case_ref}."
            )
        ).strip()

    # ─── Communication ──────────────────────────────────────────────────────

    @property
    def mandatory_disclosures(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.raw.get("communication", {}).get("mandatory_disclosures", ()))

    @property
    def fmos(self) -> dict[str, Any]:
        return dict(self.raw.get("communication", {}).get("fmos_clause", {}))

    @property
    def prohibited_phrases(self) -> tuple[str, ...]:
        return tuple(self.raw.get("communication", {}).get("prohibited_phrases", ()))

    @property
    def register(self) -> str:
        return str(self.raw.get("communication", {}).get("register", "dual"))

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(self.raw.get("communication", {}).get("languages", ("en",)))

    # ─── Meta ───────────────────────────────────────────────────────────────

    @property
    def display_name(self) -> str:
        return str(self.raw.get("display_name", self.category.replace("_", " ").title()))

    @property
    def volume_share(self) -> float | None:
        share = self.raw.get("volume_share")
        return float(share) if share is not None else None


def _describe(condition: Mapping[str, Any]) -> str:
    """Human-readable rendering of a condition, for the 'Why?' panel."""
    parts: list[str] = []
    words = {
        "gte": "at or above",
        "lte": "at or below",
        "gt": "above",
        "lt": "below",
        "equals": "is",
        "not_equals": "is not",
        "in": "is one of",
        "contains": "includes",
    }
    for field, test in condition.items():
        if isinstance(test, Mapping):
            for operator, expected in test.items():
                parts.append(f"{field.replace('_', ' ')} {words.get(operator, operator)} {expected}")
    return "; ".join(parts) or "unconditional"


# ─── Validation ─────────────────────────────────────────────────────────────


def validate(raw: Mapping[str, Any]) -> None:
    """Reject a malformed pack loudly.

    Also used by the Policy Composer before a proposed pack is allowed anywhere
    near the simulation step, so an LLM cannot emit YAML that merely looks right.
    """
    if not isinstance(raw, Mapping):
        raise RulePackError("A rule pack must be a YAML mapping.")

    category = raw.get("category")
    if category not in CATEGORIES:
        raise RulePackError(
            f"category must be one of {CATEGORIES}, got {category!r}"
        )

    try:
        version = int(raw["version"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RulePackError("version must be an integer") from exc
    if version < 1:
        raise RulePackError("version must be >= 1")

    sla = raw.get("sla")
    if not isinstance(sla, Mapping):
        raise RulePackError("sla block is required")
    for urgency in URGENCIES:
        block = sla.get(urgency)
        if not isinstance(block, Mapping) or "working_days" not in block:
            raise RulePackError(f"sla.{urgency}.working_days is required")
        days = block["working_days"]
        if not isinstance(days, int) or days < 1:
            raise RulePackError(f"sla.{urgency}.working_days must be a positive integer")

    rules = raw.get("urgency_rules")
    if not isinstance(rules, list) or not rules:
        raise RulePackError("urgency_rules must be a non-empty list")
    for index, rule in enumerate(rules):
        if "default" in rule:
            if rule["default"] not in URGENCIES:
                raise RulePackError(f"urgency_rules[{index}].default must be one of {URGENCIES}")
            continue
        if "when" not in rule or "then" not in rule:
            raise RulePackError(f"urgency_rules[{index}] needs both 'when' and 'then'")
        if rule["then"] not in URGENCIES:
            raise RulePackError(f"urgency_rules[{index}].then must be one of {URGENCIES}")

    verification = raw.get("verification", {})
    floor = verification.get("confidence_floor", 0.75)
    if not isinstance(floor, (int, float)) or not 0.0 <= float(floor) <= 1.0:
        raise RulePackError("verification.confidence_floor must be between 0 and 1")

    resolution = raw.get("resolution", {})
    if resolution.get("require_verification", "PASS") != "PASS":
        raise RulePackError(
            "resolution.require_verification must be 'PASS'. Money never moves on an "
            "unverified case."
        )
    if resolution.get("journal_type") not in (None, "REVERSAL", "CREDIT_ADJUSTMENT"):
        raise RulePackError(
            "resolution.journal_type must be REVERSAL or CREDIT_ADJUSTMENT"
        )

    communication = raw.get("communication", {})
    disclosures = communication.get("mandatory_disclosures")
    if not disclosures:
        raise RulePackError("communication.mandatory_disclosures must not be empty")

    seen_ids: set[str] = set()
    for index, disclosure in enumerate(disclosures):
        if not isinstance(disclosure, Mapping) or not disclosure.get("id"):
            raise RulePackError(
                f"communication.mandatory_disclosures[{index}] must be a mapping with an id"
            )
        disclosure_id = str(disclosure["id"])
        if disclosure_id in seen_ids:
            raise RulePackError(f"duplicate disclosure id {disclosure_id!r}")
        seen_ids.add(disclosure_id)

        unknown = set(disclosure) - DISCLOSURE_KEYS
        if unknown:
            raise RulePackError(
                f"disclosure {disclosure_id!r} declares unsupported check(s) "
                f"{sorted(unknown)}. The linter would not evaluate them and the "
                f"disclosure would silently pass, so the pack is rejected."
            )
        if not set(disclosure) & DISCLOSURE_CHECKS:
            raise RulePackError(
                f"disclosure {disclosure_id!r} states a requirement but checks nothing. "
                f"Use one of {sorted(DISCLOSURE_CHECKS)}."
            )

        unknown_outcomes = set(disclosure.get("applies_when_outcome_in", ())) - set(OUTCOMES)
        if unknown_outcomes:
            raise RulePackError(
                f"disclosure {disclosure_id!r} is conditioned on outcome(s) "
                f"{sorted(unknown_outcomes)}, which the case_outcome enum cannot "
                f"produce. Expected some of {list(OUTCOMES)}."
            )

    fmos = communication.get("fmos_clause")
    if not isinstance(fmos, Mapping) or not fmos.get("text_en"):
        raise RulePackError("communication.fmos_clause with text_en is required")
    if int(fmos.get("window_months", 0)) != 6:
        raise RulePackError(
            "communication.fmos_clause.window_months must be 6 — the FMOS referral "
            "window is set by the scheme, not by the bank."
        )

    fmos_outcomes = set(fmos.get("applies_when", {}).get("outcome_in", ())) - set(OUTCOMES)
    if fmos_outcomes:
        raise RulePackError(
            f"communication.fmos_clause.applies_when.outcome_in names unknown "
            f"outcome(s) {sorted(fmos_outcomes)}. Expected some of {list(OUTCOMES)}."
        )

    if raw.get("audit", {}).get("hash_chain") != "required":
        raise RulePackError("audit.hash_chain must be 'required'")


# ─── Loading ────────────────────────────────────────────────────────────────


def load_yaml(text: str) -> RulePack:
    """Parse, validate and wrap. Raises RulePackError on anything malformed."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulePackError(f"Invalid YAML: {exc}") from exc
    validate(raw)
    return RulePack(
        category=raw["category"],
        version=int(raw["version"]),
        raw=dict(raw),
        source_yaml=text,
    )


def load_file(path: Path) -> RulePack:
    return load_yaml(path.read_text())


def load_all(directory: Path | None = None) -> dict[str, RulePack]:
    """Load every pack from disk, keyed by category."""
    target = directory or RULE_PACKS_DIR
    packs: dict[str, RulePack] = {}
    for path in sorted(target.glob("*.yaml")):
        pack = load_file(path)
        packs[pack.category] = pack
    return packs


def missing_categories(packs: Iterable[str]) -> tuple[str, ...]:
    """Which of the seven spec categories still have no pack."""
    present = set(packs)
    return tuple(c for c in CATEGORIES if c not in present)
