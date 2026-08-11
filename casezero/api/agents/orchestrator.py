"""The pipeline. One complaint in, one auditable case out.

The orchestrator is deliberately thin. It owns three things the agents are not
allowed to own, and nothing else:

* **Status changes**, each guarded by `gates.assert_transition`. There is no path
  from RECEIVED to FINANCIALLY_RESOLVED, and no route to FINANCIALLY_RESOLVED at
  all unless verification returned PASS.
* **The chain.** Every event any agent produced is appended here, in order,
  through `db.append_event`. That single chokepoint is why `verify_chain` means
  something: a state change that skipped it would leave no link, and a chain with
  a hole in it is not evidence.
* **Routing.** Which of the four destinations a case reaches — quarantined,
  resolved and communicated, rejected and communicated, or waiting for a human.

Everything else is a decision, and decisions belong to the kernel.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from api.agents import classifier, communicator, intake, resolver, verifier
from api.agents.base import AgentContext, Event
from api.kernel import gates
from api.kernel.chain import ChainVerdict

#: Statuses from which a customer letter may be released.
COMMUNICABLE = ("FINANCIALLY_RESOLVED", "REVIEW_PENDING")


@dataclass
class CaseRun:
    """The result of one pass through the pipeline."""

    case_id: str | None = None
    case_ref: str = ""
    status: str = "RECEIVED"
    category: str | None = None
    urgency: str | None = None
    confidence: float | None = None
    verification_result: str | None = None
    outcome: str = "PENDING"
    posted: bool = False
    amount_rm: float | None = None
    sla_due: str | None = None
    quarantined: bool = False
    letter: str = ""
    events: list[Event] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    cost_rm: float = 0.0
    degraded: list[str] = field(default_factory=list)
    intake: Any = None
    classification: Any = None
    verification: Any = None
    resolution: Any = None
    communication: Any = None

    @property
    def needs_human(self) -> bool:
        return self.status == "REVIEW_PENDING"

    def timeline(self) -> list[dict[str, Any]]:
        return [{"type": e.type, "actor": e.actor, "payload": e.payload} for e in self.events]


class Orchestrator:
    """Runs the six agents in order, writing the chain as it goes."""

    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    # ─── Chain + status ─────────────────────────────────────────────────────

    def _append(self, run: CaseRun, events: list[Event]) -> None:
        for event in events:
            run.events.append(event)
            if self.ctx.db is not None and run.case_id:
                self.ctx.db.append_event(run.case_id, event.type, event.actor, event.payload)

    def _transition(
        self,
        run: CaseRun,
        target: str,
        *,
        fields: dict[str, Any] | None = None,
        actor: str,
        reason: str,
    ) -> None:
        """Move the case, or refuse to.

        `assert_transition` raises on an illegal move and on any attempt to reach
        FINANCIALLY_RESOLVED without a PASS. Letting that exception escape is
        intentional: a pipeline that cannot make a legal move must stop, not
        improvise.
        """
        gates.assert_transition(
            run.status, target, verification_result=run.verification_result
        )
        payload = {"from": run.status, "to": target, "reason": reason}
        run.status = target
        if self.ctx.db is not None and run.case_id:
            self.ctx.db.update_case(run.case_id, status=target, **(fields or {}))
        self._append(run, [Event(type="STATUS_CHANGED", actor=actor, payload=payload)])

    # ─── The pipeline ───────────────────────────────────────────────────────

    async def process(
        self,
        raw: bytes | str,
        *,
        channel: str = "MANUAL_INJECT",
        approved_by: str | None = None,
        dual_control_by: str | None = None,
        on_case_created: Callable[[str, str], None] | None = None,
    ) -> CaseRun:
        ctx = self.ctx
        ctx.begin_run()
        run = CaseRun()

        # ── 1. Intake, with the firewall ahead of every model call ──────────
        parsed = await intake.run(raw, ctx, channel=channel)
        run.intake = parsed
        run.amount_rm = parsed.extracted.amount_rm

        case = ctx.db.create_case(status="RECEIVED", **parsed.case_fields())
        run.case_id = str(case["id"])
        run.case_ref = str(case.get("case_ref", ""))
        ctx.bind_case(run.case_id)
        if on_case_created is not None:
            # Lets a caller publish progress while this pipeline is still running.
            # A bookkeeping failure must never abort a case that is mid-flight.
            try:
                on_case_created(run.case_id, run.case_ref)
            except Exception:  # noqa: BLE001 - progress reporting is best-effort
                pass
        self._append(run, parsed.events)

        if parsed.hostile:
            return self._quarantine(run, parsed)

        # ── 2. Classification. The model proposes; the pack decides ─────────
        classification = await classifier.run(
            parsed, ctx, exclude_case_id=run.case_id
        )
        run.classification = classification
        run.category = classification.category
        run.urgency = classification.urgency
        run.confidence = classification.confidence
        run.sla_due = classification.sla.due.isoformat()

        fields = classification.case_fields()
        if classification.facts.get("customer_id"):
            fields["customer_id"] = classification.facts["customer_id"]
        self._transition(
            run,
            "CLASSIFIED",
            fields=fields,
            actor=classifier.ACTOR,
            reason=f"Classified as {classification.category} "
                   f"({classification.confidence:.2f}); urgency "
                   f"{classification.urgency}.",
        )
        self._append(run, classification.events)

        # ── 3. Verification against core banking ────────────────────────────
        verification = await verifier.run(parsed, classification, ctx)
        run.verification = verification
        run.verification_result = verification.result
        run.tool_calls.extend(verification.tool_calls)

        self._transition(
            run,
            "VERIFIED",
            fields={"verification_result": verification.result},
            actor=verifier.ACTOR,
            reason=f"Core banking returned {verification.result}.",
        )
        self._append(run, verification.events)

        # ── 4. Resolution, gated and ticketed ───────────────────────────────
        resolution = await resolver.run(
            case | {"id": run.case_id, "case_ref": run.case_ref},
            parsed,
            classification,
            verification,
            ctx,
            approved_by=approved_by,
            dual_control_by=dual_control_by,
        )
        run.resolution = resolution
        run.outcome = resolution.outcome
        run.posted = resolution.posted

        resolution_fields: dict[str, Any] = {"outcome": resolution.outcome}
        if resolution.posted:
            resolution_fields["resolved_at"] = datetime.now(timezone.utc).isoformat()
        self._transition(
            run,
            resolution.target_status,
            fields=resolution_fields,
            actor=resolver.ACTOR,
            reason=resolution.decision.explain(),
        )
        self._append(run, resolution.events)

        # ── 5. Communication, linted and gated ──────────────────────────────
        # A case waiting on a human decision is not written to yet: there is
        # nothing to tell the customer until the decision exists.
        if resolution.outcome == "PENDING":
            run.cost_rm = ctx.cost_rm
            run.degraded = list(ctx.degraded)
            return run

        communication = await communicator.run(
            case | {"case_ref": run.case_ref},
            classification,
            verification,
            ctx,
            outcome=resolution.outcome,
            summary=parsed.extracted.summary or parsed.subject,
            customer_name=classification.facts.get("customer_name"),
            amount_rm=parsed.extracted.amount_rm,
        )
        run.communication = communication
        run.letter = communication.body
        self._append(run, communication.events)

        if communication.sent:
            self._transition(
                run,
                "COMMUNICATED",
                actor=communicator.ACTOR,
                reason=f"Compliance lint passed ({communication.report.summary()}).",
            )

        run.cost_rm = ctx.cost_rm
        run.degraded = list(ctx.degraded)
        return run

    # ─── Quarantine ─────────────────────────────────────────────────────────

    def _quarantine(self, run: CaseRun, parsed: Any) -> CaseRun:
        """Preserve the hostile input and stop the case here.

        The excerpt is kept deliberately. An attack that leaves no artefact is
        indistinguishable from an attack nobody noticed, and the quarantine table
        is what the demo opens to show the difference.
        """
        verdict = parsed.verdict
        if self.ctx.db is not None:
            self.ctx.db.quarantine_case(
                case_id=run.case_id,
                reason=verdict.reason(),
                detector=",".join(verdict.detectors),
                raw_excerpt=parsed.body[:4000],
            )
        self._transition(
            run,
            "QUARANTINED",
            actor=intake.ACTOR,
            reason="Prompt-injection firewall blocked this input before any model "
                   "call.",
        )
        run.quarantined = True
        run.cost_rm = self.ctx.cost_rm
        run.degraded = list(self.ctx.degraded)
        return run

    # ─── Verification of our own work ───────────────────────────────────────

    def verify_chain(self, run: CaseRun) -> ChainVerdict:
        return self.ctx.db.verify_case_chain(run.case_id)


async def process_email(
    raw: bytes | str,
    ctx: AgentContext | None = None,
    *,
    channel: str = "MANUAL_INJECT",
) -> CaseRun:
    """Convenience entry point for the API and the .eml replay tooling."""
    from api.agents.base import build_context

    return await Orchestrator(ctx or build_context()).process(raw, channel=channel)
