"""Agent 3 — Verifier. Asks the ledger, not the model.

This agent makes no model calls at all, and that is a design decision rather than
an omission. The question it answers — does the bank's own record support what the
customer says happened — has a correct answer sitting in a table. Asking a language
model to weigh evidence it cannot see would add a failure mode and remove an
auditable one.

So the verifier is an MCP client. It reads the tolerance and the required evidence
out of the rule pack, calls `core-banking.verify_claim`, and returns the tool's
verdict with the rows behind it attached. Every claim it makes carries a citation
to either a ledger row or a rule-pack key.

Its most important behaviour is what it does when it cannot get an answer. Per the
agent contract, a tool failure, an ambiguous match or a missing account number all
produce `MANUAL_REVIEW` — never a default to PASS, and never a silent skip. An
unreachable core banking system is a reason to ask a person, not a reason to
believe the customer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.agents.base import Event, agent_actor
from api.agents.classifier import ClassifierResult
from api.agents.intake import IntakeResult
from api.kernel.rules import RulePack
from api.security.crypto import mask_account

ACTOR = agent_actor("verifier")

VERDICTS = ("PASS", "FAIL", "MANUAL_REVIEW")


@dataclass
class Evidence:
    """One checkable statement, with where it came from."""

    source: str
    field: str
    expected: Any
    found: Any
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "field": self.field,
            "expected": self.expected,
            "found": self.found,
            "ok": self.ok,
        }


@dataclass
class VerifierResult:
    result: str
    reasons: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    matched: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.result == "PASS"

    @property
    def txn_ref(self) -> str | None:
        return (self.matched or {}).get("txn_ref")

    def rationale(self) -> str:
        return " ".join(self.reasons) or "No evidence was returned."

    def as_payload(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "reasons": self.reasons,
            "evidence": [e.as_dict() for e in self.evidence],
            "matched": self.matched,
            "candidate_count": len(self.candidates),
            "citations": self.citations,
            "tool_calls": self.tool_calls,
        }


def _fallback(pack: RulePack, reason: str, citation: str) -> VerifierResult:
    """The pack's declared behaviour when the evidence will not settle it."""
    verdict = pack.fallback_on_ambiguity
    if verdict not in VERDICTS:
        verdict = "MANUAL_REVIEW"
    return VerifierResult(
        result=verdict,
        reasons=[reason],
        citations=[
            citation,
            f"{pack.category}.verification.fallback_on_ambiguity = {verdict}",
        ],
    )


async def run(
    intake: IntakeResult,
    classification: ClassifierResult,
    ctx: Any,
) -> VerifierResult:
    pack = classification.pack
    claim = intake.extracted
    account_no = claim.account_no

    if not account_no:
        result = _fallback(
            pack,
            "No account number could be read from the complaint, so there is "
            "nothing to check the claim against.",
            f"{pack.category}.verification.required_evidence = account_exists",
        )
    else:
        arguments: dict[str, Any] = {
            "account_no": account_no,
            "amount_rm": claim.amount_rm,
            "txn_ref": claim.txn_refs[0] if claim.txn_refs else None,
            "merchant": claim.merchant or None,
            "tolerance_pct": pack.amount_tolerance_pct,
            "required_evidence": list(pack.required_evidence),
        }
        try:
            payload = await ctx.call_tool("core-banking", "verify_claim", **arguments)
        except Exception as exc:  # noqa: BLE001 - see the module docstring
            result = _fallback(
                pack,
                f"Core banking could not be reached ({exc}). The claim is neither "
                f"supported nor contradicted, so it goes to a person.",
                f"{pack.category}.verification.fallback_on_ambiguity",
            )
            result.tool_calls.append(
                {
                    "server": "core-banking",
                    "tool": "verify_claim",
                    "arguments": {**arguments, "account_no": mask_account(account_no)},
                    "ok": False,
                    "error": str(exc),
                }
            )
        else:
            result = _from_payload(payload, pack, claim)
            result.tool_calls.append(
                {
                    "server": "core-banking",
                    "tool": "verify_claim",
                    "arguments": {**arguments, "account_no": mask_account(account_no)},
                    "ok": True,
                    "transport": getattr(ctx.gateway, "transport", "unknown"),
                }
            )

    result.events.append(
        Event(
            type="VERIFICATION_COMPLETED",
            actor=ACTOR,
            payload=result.as_payload(),
        )
    )
    return result


def _from_payload(payload: dict[str, Any], pack: RulePack, claim: Any) -> VerifierResult:
    """Turn the tool's answer into evidence rows the review queue can render."""
    verdict = str(payload.get("verdict") or "MANUAL_REVIEW")
    if verdict not in VERDICTS:
        verdict = "MANUAL_REVIEW"

    matched = payload.get("matched")
    proven = set(payload.get("evidence") or ())

    evidence = [
        Evidence(
            source="core-banking.verify_claim",
            field="account_exists",
            expected=True,
            found="account_exists" in proven,
            ok="account_exists" in proven,
        )
    ]

    if claim.txn_refs:
        evidence.append(
            Evidence(
                source="core-banking.verify_claim",
                field="txn_ref",
                expected=claim.txn_refs[0],
                found=(matched or {}).get("txn_ref"),
                ok="txn_ref_found" in proven,
            )
        )
    if claim.amount_rm is not None:
        evidence.append(
            Evidence(
                source="core-banking.verify_claim",
                field="amount_rm",
                expected=float(claim.amount_rm),
                found=(matched or {}).get("amount_rm"),
                ok="amount_matches" in proven,
            )
        )
    if claim.merchant:
        evidence.append(
            Evidence(
                source="core-banking.verify_claim",
                field="merchant",
                expected=claim.merchant,
                found=(matched or {}).get("merchant"),
                ok="merchant_matches" in proven,
            )
        )
    evidence.append(
        Evidence(
            source="core-banking.verify_claim",
            field="not_already_disputed",
            expected=True,
            found="not_already_disputed" in proven,
            ok="not_already_disputed" in proven,
        )
    )

    citations = [
        f"{pack.category}.verification.required_evidence = "
        f"{list(pack.required_evidence)}",
        f"{pack.category}.verification.amount_tolerance_pct = "
        f"{pack.amount_tolerance_pct}",
    ]
    if matched and matched.get("txn_ref"):
        citations.append(f"core-banking:transactions.txn_ref = {matched['txn_ref']}")

    return VerifierResult(
        result=verdict,
        reasons=list(payload.get("reasons") or []),
        evidence=evidence,
        matched=matched,
        candidates=list(payload.get("candidates") or []),
        citations=citations,
    )
