"""Agent 4 — Resolver. The only path from a decision to a payment.

The resolver does not decide anything. It asks `kernel/gates.authorize_resolution`,
and the ruling it gets back determines which of three things happens: a posting, a
review task, or a refusal.

The interesting part is what a `POST` ruling produces. It is not a boolean the next
line of code can ignore — it mints an HMAC-signed ticket bound to this case, this
account, this amount and this entry type, valid for two minutes. The core-banking
tool refuses to post without one. So the guarantee survives leaving the process: an
agent that has been argued into calling `post_adjustment` on its own still cannot
post, because it has no way to produce the signature.

`_mint` below refuses to issue a ticket for anything other than a POST ruling, so
there is exactly one route from the gate to the money.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from api.agents.base import KERNEL, Event, agent_actor
from api.agents.classifier import ClassifierResult
from api.agents.intake import IntakeResult
from api.agents.verifier import VerifierResult
from api.kernel import gates, tickets
from api.kernel.gates import GateDecision
from api.kernel.rules import RulePack
from api.security.crypto import mask_account

ACTOR = agent_actor("resolver")

#: Who the ticket says issued it. Not an agent — the gate.
TICKET_ISSUER = "kernel:gates.authorize_resolution"


@dataclass
class ResolverResult:
    """The gate's ruling, and whatever followed from it."""

    decision: GateDecision
    #: FINANCIALLY_RESOLVED | REVIEW_PENDING
    target_status: str
    #: RESOLVED_IN_FULL | REJECTED | PENDING
    outcome: str
    posted: bool = False
    entry: dict[str, Any] | None = None
    amount_rm: float | None = None
    events: list[Event] = field(default_factory=list)

    @property
    def needs_human(self) -> bool:
        return self.target_status == "REVIEW_PENDING"

    def case_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {"outcome": self.outcome}
        if self.posted:
            fields["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return fields


def narrative(pack: RulePack, *, case_ref: str, txn_ref: str | None) -> str:
    """Fill the pack's narrative template without exploding on a missing field."""
    values: dict[str, Any] = defaultdict(str)
    values.update({"case_ref": case_ref, "txn_ref": txn_ref or "(no reference quoted)"})
    text = pack.narrative_template.format_map(values).strip()
    return " ".join(text.split())


def _mint(
    decision: GateDecision,
    *,
    case_id: str,
    account_no: str,
    amount_rm: float,
    entry_type: str,
) -> str:
    """Mint the capability. Refuses on anything but a POST ruling.

    Keeping this in one function, guarded, is what makes "money moves only on a
    gate decision" a property of the code rather than a convention.
    """
    if decision.action != "POST":
        raise PermissionError(
            f"Refusing to mint an authorisation ticket for a {decision.action} "
            f"ruling. {decision.explain()}"
        )
    return tickets.issue(
        case_id=case_id,
        account_no=account_no,
        amount_rm=amount_rm,
        entry_type=entry_type,
        issued_by=TICKET_ISSUER,
    )


async def run(
    case: dict[str, Any],
    intake: IntakeResult,
    classification: ClassifierResult,
    verification: VerifierResult,
    ctx: Any,
    *,
    approved_by: str | None = None,
    dual_control_by: str | None = None,
) -> ResolverResult:
    pack = classification.pack
    amount_rm = intake.extracted.amount_rm
    account_no = intake.extracted.account_no
    case_id = str(case["id"])
    case_ref = str(case.get("case_ref", ""))

    decision = gates.authorize_resolution(
        pack,
        verification_result=verification.result,
        confidence=classification.confidence,
        amount_rm=amount_rm,
        approved_by=approved_by,
        dual_control_by=dual_control_by,
    )

    # A bank administrator can pause autonomous financial resolution without
    # editing policy packs. This control only narrows authority: a PASS case is
    # routed to review and still needs a human to resume through the same gate.
    controls_reader = getattr(ctx.db, "get_stakeholder_settings", None)
    if controls_reader is not None and decision.action == "POST" and not approved_by:
        controls = controls_reader()
        if not controls.get("automatic_resolution_enabled", True):
            decision = GateDecision(
                action="MANUAL_REVIEW",
                reasons=(
                    "Verification and category policy permit resolution, but the "
                    "stakeholder control register has paused autonomous posting.",
                ),
                citations=(
                    "stakeholder_settings.automatic_resolution_enabled = false",
                ),
            )

    events = [
        Event(
            type="GATE_DECISION",
            actor=KERNEL,
            payload={
                "gate": "authorize_resolution",
                "action": decision.action,
                "requires_dual_control": decision.requires_dual_control,
                "reasons": list(decision.reasons),
                "citations": list(decision.citations),
                "inputs": {
                    "verification_result": verification.result,
                    "confidence": round(float(classification.confidence), 3),
                    "amount_rm": amount_rm,
                    "approved_by": approved_by,
                    "dual_control_by": dual_control_by,
                },
            },
        )
    ]

    if decision.action != "POST":
        # DENY still routes to a human: a refusal is a decision the customer must
        # be told about, and the state machine has no path from VERIFIED straight
        # to COMMUNICATED.
        outcome = "REJECTED" if decision.action == "DENY" else "PENDING"
        events.append(
            Event(
                type="REVIEW_REQUESTED",
                actor=KERNEL,
                payload={
                    "because": decision.explain(),
                    "requires_dual_control": decision.requires_dual_control,
                    "proposed_amount_rm": amount_rm,
                    "citations": list(decision.citations),
                },
            )
        )
        return ResolverResult(
            decision=decision,
            target_status="REVIEW_PENDING",
            outcome=outcome,
            amount_rm=amount_rm,
            events=events,
        )

    # From here the gate has said POST, so an account number and a positive
    # amount are guaranteed by the checks it ran.
    assert account_no and amount_rm  # noqa: S101 - documents a gate postcondition

    entry_type = pack.journal_type
    ticket = _mint(
        decision,
        case_id=case_id,
        account_no=account_no,
        amount_rm=float(amount_rm),
        entry_type=entry_type,
    )

    try:
        posting = await ctx.call_tool(
            "core-banking",
            "post_adjustment",
            case_id=case_id,
            account_no=account_no,
            entry_type=entry_type,
            debit_account=pack.debit_account,
            amount_rm=float(amount_rm),
            narrative=narrative(pack, case_ref=case_ref, txn_ref=verification.txn_ref),
            posted_by=ACTOR,
            authorisation=ticket,
            dual_control_by=dual_control_by,
            txn_ref=verification.txn_ref,
        )
    except Exception as exc:  # noqa: BLE001 - a refused posting is not a resolved case
        events.append(
            Event(
                type="POSTING_REFUSED",
                actor=KERNEL,
                payload={
                    "error": str(exc),
                    "amount_rm": amount_rm,
                    "account_no_masked": mask_account(account_no),
                    "note": "The gate authorised the posting but core banking "
                            "refused it. No funds moved.",
                },
            )
        )
        return ResolverResult(
            decision=decision,
            target_status="REVIEW_PENDING",
            outcome="PENDING",
            amount_rm=amount_rm,
            events=events,
        )

    entry = posting.get("entry")
    events.append(
        Event(
            type="JOURNAL_POSTED",
            actor=ACTOR,
            payload={
                "posted": bool(posting.get("posted")),
                "idempotent_replay": not posting.get("posted", False),
                "entry_type": entry_type,
                "amount_rm": float(amount_rm),
                "debit_account": pack.debit_account,
                "credit_account_masked": mask_account(account_no),
                "narrative": (entry or {}).get("narrative"),
                "balanced": bool(posting.get("balanced")),
                "authorised_by": posting.get("authorised_by_ticket"),
                "dual_control_by": dual_control_by,
                "citations": list(decision.citations)
                + [f"{pack.category}.resolution.journal_type = {entry_type}"],
            },
        )
    )

    return ResolverResult(
        decision=decision,
        target_status="FINANCIALLY_RESOLVED",
        outcome="RESOLVED_IN_FULL",
        posted=True,
        entry=entry,
        amount_rm=float(amount_rm),
        events=events,
    )
