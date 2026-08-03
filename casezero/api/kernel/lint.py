"""Outbound message linting.

The LLM writes the human half of a customer letter. This module owns the
regulatory half, and no message reaches a customer without passing through it.

The distinction matters: a model *asked* to include the FMOS clause will include it
almost always, and "almost always" is not a compliance posture. Here the clause is
inserted deterministically and its absence blocks the send, so the guarantee comes
from control flow rather than from prompt obedience.

Deterministic and LLM-free. Covered by api/tests/test_lint.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from api.kernel.rules import RulePack

Status = Literal["PASS", "FAIL", "FIXED"]

#: Outcomes that oblige the bank to tell the customer about the ombudsman.
FMOS_TRIGGER_OUTCOMES = ("REJECTED", "PARTIALLY_RESOLVED", "CUSTOMER_DISSATISFIED")


@dataclass(frozen=True)
class Finding:
    """One rule, one verdict. Rendered as a lint badge beside the draft."""

    rule_id: str
    requirement: str
    status: Status
    detail: str

    @property
    def ok(self) -> bool:
        return self.status in ("PASS", "FIXED")


@dataclass
class LintReport:
    """The result of linting a draft, plus the repaired body."""

    body: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """True when at least one requirement could not be satisfied."""
        return any(f.status == "FAIL" for f in self.findings)

    @property
    def ok(self) -> bool:
        return not self.blocked

    @property
    def repaired(self) -> bool:
        return any(f.status == "FIXED" for f in self.findings)

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "FAIL"]

    def summary(self) -> str:
        passed = sum(1 for f in self.findings if f.status == "PASS")
        fixed = sum(1 for f in self.findings if f.status == "FIXED")
        failed = len(self.failures)
        parts = [f"{passed} passed"]
        if fixed:
            parts.append(f"{fixed} auto-inserted")
        if failed:
            parts.append(f"{failed} BLOCKED")
        return ", ".join(parts)


@dataclass(frozen=True)
class LintContext:
    """Everything the linter needs to check a draft against reality.

    `due_date_display` is a rendered date rather than a duration because a customer
    letter promising "within 5 working days" is not the same as one naming a date,
    and BNM expects the date.
    """

    case_ref: str
    amount_rm: float | None = None
    outcome: str = "PENDING"
    due_date_display: str | None = None
    language: str = "en"


def _normalise(text: str) -> str:
    """Collapse whitespace and case so a check is about content, not formatting."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _contains(body: str, needle: str) -> bool:
    return _normalise(needle) in _normalise(body)


# ─── FMOS ───────────────────────────────────────────────────────────────────


def fmos_applies(pack: RulePack, context: LintContext) -> bool:
    """Whether this message must carry the ombudsman referral clause.

    Attached on rejection, partial resolution and dissatisfaction — the situations
    where the customer's next step is outside the bank.
    """
    fmos = pack.fmos
    if not fmos:
        return False

    applies_when = fmos.get("applies_when", {})

    ceiling = applies_when.get("claim_amount_rm", {}).get("lte")
    if ceiling is not None and context.amount_rm is not None:
        if float(context.amount_rm) > float(ceiling):
            return False

    outcomes = applies_when.get("outcome_in") or FMOS_TRIGGER_OUTCOMES
    return context.outcome in outcomes


def render_fmos_block(pack: RulePack) -> str:
    """The clause as it will appear, in every configured language."""
    fmos = pack.fmos
    blocks: list[str] = []

    english = (fmos.get("text_en") or "").strip()
    if english:
        blocks.append(english)

    if "ms" in pack.languages:
        malay = (fmos.get("text_ms") or "").strip()
        if malay:
            blocks.append(malay)

    return "\n\n".join(blocks)


def _fmos_present(body: str, pack: RulePack) -> bool:
    """Detect the clause by substance, not by exact wording.

    An LLM that paraphrases the clause has still discharged the obligation, so
    matching on the two load-bearing facts — the scheme and the six-month window —
    avoids rejecting a correct letter for cosmetic reasons.
    """
    normalised = _normalise(body)
    names_scheme = "financial markets ombudsman" in normalised or "fmos" in normalised
    states_window = bool(
        re.search(r"\b(six|6)\s*(\(\s*6\s*\))?\s*month", normalised)
        or "enam (6) bulan" in normalised
        or "enam bulan" in normalised
    )
    return names_scheme and states_window


# ─── Disclosure checks ──────────────────────────────────────────────────────


def disclosure_applies(disclosure: Mapping[str, Any], context: LintContext) -> bool:
    """Some disclosures are outcome-specific.

    Telling a customer we attempted a DuitNow recall is required when we did; saying
    it on an unrelated letter is noise. A disclosure that does not apply produces no
    finding at all rather than a vacuous PASS, so the lint badge stays honest.
    """
    outcomes = disclosure.get("applies_when_outcome_in")
    if not outcomes:
        return True
    return context.outcome in tuple(outcomes)


def amount_renderings(amount: float) -> tuple[str, ...]:
    """The ways a letter might legitimately write RM 2,450.00.

    Public because the communicator reads it too: it only adds its own "the
    amount in dispute is" sentence when the figure is not already stated. Sharing
    the definition is what stops the writer and the checker drifting apart.
    """
    return (f"{amount:,.2f}", f"{amount:.2f}")


def _check_disclosure(
    disclosure: Mapping[str, Any],
    body: str,
    context: LintContext,
) -> Finding:
    rule_id = str(disclosure.get("id", "UNNAMED"))
    requirement = str(disclosure.get("requirement", rule_id))

    missing: list[str] = []

    for needle in disclosure.get("text_contains", ()):
        if not _contains(body, str(needle)):
            missing.append(f"missing phrase {needle!r}")

    if disclosure.get("must_include_case_ref"):
        if context.case_ref and context.case_ref.lower() not in body.lower():
            missing.append(f"case reference {context.case_ref} is absent")

    if disclosure.get("must_state_deadline_date"):
        if not context.due_date_display:
            missing.append("no deadline was computed for this case")
        elif not _contains(body, context.due_date_display):
            missing.append(
                f"deadline date {context.due_date_display!r} is absent — a duration "
                f"is not sufficient"
            )

    if disclosure.get("must_state_amount"):
        if context.amount_rm is None:
            missing.append("no disputed amount is on the case")
        else:
            renderings = amount_renderings(float(context.amount_rm))
            if not any(_contains(body, r) for r in renderings):
                missing.append(
                    f"the amount {renderings[0]} is not stated in figures"
                )

    if missing:
        return Finding(rule_id, requirement, "FAIL", "; ".join(missing))
    return Finding(rule_id, requirement, "PASS", "Satisfied.")


# ─── Entry point ────────────────────────────────────────────────────────────


def lint_outbound(pack: RulePack, body: str, context: LintContext) -> LintReport:
    """Lint a draft, inserting the FMOS clause when it is required and absent.

    Returns the possibly-repaired body. A report with `blocked=True` must never be
    sent — `api/kernel/gates.py` refuses to release it.
    """
    report = LintReport(body=body)

    # 1. Prohibited phrases. Checked first: no amount of repair makes an
    #    over-promising letter acceptable.
    for phrase in pack.prohibited_phrases:
        if _contains(report.body, phrase):
            report.findings.append(
                Finding(
                    rule_id="PROHIBITED_PHRASE",
                    requirement=f"Must not contain {phrase!r}",
                    status="FAIL",
                    detail=f"Found prohibited phrase {phrase!r}. A customer letter "
                           f"cannot make this commitment.",
                )
            )

    # 2. The FMOS clause. Inserted rather than merely demanded.
    if fmos_applies(pack, context):
        if _fmos_present(report.body, pack):
            report.findings.append(
                Finding(
                    rule_id="FMOS_CLAUSE",
                    requirement="Inform the customer of their FMOS referral right "
                                "within six months.",
                    status="PASS",
                    detail="Clause already present in the draft.",
                )
            )
        else:
            block = render_fmos_block(pack)
            enforcement = str(pack.fmos.get("enforcement", ""))
            if block:
                report.body = report.body.rstrip() + "\n\n" + block + "\n"
                report.findings.append(
                    Finding(
                        rule_id="FMOS_CLAUSE",
                        requirement="Inform the customer of their FMOS referral right "
                                    "within six months.",
                        status="FIXED",
                        detail="Clause was absent and has been inserted verbatim from "
                               "the rule pack.",
                    )
                )
            else:
                # Enforcement says block if absent, and there is no text to insert.
                report.findings.append(
                    Finding(
                        rule_id="FMOS_CLAUSE",
                        requirement="Inform the customer of their FMOS referral right.",
                        status="FAIL",
                        detail=f"Clause is required ({enforcement}) but the rule pack "
                               f"provides no text to insert.",
                    )
                )

    # 3. Mandatory disclosures, checked against the repaired body so an inserted
    #    clause can satisfy a disclosure that depends on it.
    for disclosure in pack.mandatory_disclosures:
        if not disclosure_applies(disclosure, context):
            continue
        report.findings.append(_check_disclosure(disclosure, report.body, context))

    return report


def lint_or_raise(pack: RulePack, body: str, context: LintContext) -> str:
    """Convenience wrapper for callers that treat a lint failure as fatal."""
    report = lint_outbound(pack, body, context)
    if report.blocked:
        reasons = "; ".join(f"{f.rule_id}: {f.detail}" for f in report.failures)
        raise ValueError(f"Outbound message blocked by compliance lint — {reasons}")
    return report.body
