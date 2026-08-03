"""Agent 6 — Supervisor. Escalates before the deadline, not after it.

A watchdog that fires when an SLA is breached has already failed; the breach is
the thing it was supposed to prevent. So this agent forecasts: it recomputes each
open case's remaining working-day budget and escalates while there is still time
to act, at the threshold the rule pack declares.

It is read-only on money by construction — it holds no ticket, calls no posting
tool, and returns escalations for humans rather than actions for machines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, Sequence

from api.agents.base import KERNEL, Event, agent_actor
from api.kernel.rules import RulePack
from api.kernel.sla import SlaWindow, forecast_breach, is_working_day

ACTOR = agent_actor("supervisor")

#: Statuses that no longer consume the clock.
TERMINAL = ("COMMUNICATED", "CLOSED", "QUARANTINED")


def _parse(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def window_from_case(case: dict[str, Any], holidays: set[date] | None = None) -> SlaWindow | None:
    """Rebuild the SLA window from what was stored when the case was classified.

    Rebuilt rather than recomputed: the deadline a customer was told is the one
    that must be tracked, even if the pack's working-day table changes afterwards.
    """
    start = _parse(case.get("sla_start"))
    due = _parse(case.get("sla_due"))
    working_days = case.get("sla_working_days")
    if not start or not due or not working_days:
        return None

    calendar: list[tuple[date, bool]] = []
    cursor = start.date()
    while cursor <= due.date():
        calendar.append((cursor, is_working_day(cursor, holidays)))
        cursor = date.fromordinal(cursor.toordinal() + 1)

    return SlaWindow(
        start=start, due=due, working_days=int(working_days), calendar=tuple(calendar)
    )


@dataclass
class Escalation:
    """One case running out of time."""

    case_id: str
    case_ref: str
    status: str
    urgency: str
    category: str
    fraction_remaining: float
    due: datetime
    threshold: float
    breached: bool

    @property
    def pct_remaining(self) -> int:
        return int(round(self.fraction_remaining * 100))

    def message(self) -> str:
        if self.breached:
            return (
                f"{self.case_ref} has passed its {self.urgency} SLA "
                f"({self.due.date().isoformat()}) and is still {self.status}."
            )
        return (
            f"{self.case_ref} has {self.pct_remaining}% of its {self.urgency} SLA "
            f"budget left and is due {self.due.date().isoformat()}."
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "case_ref": self.case_ref,
            "status": self.status,
            "urgency": self.urgency,
            "category": self.category,
            "fraction_remaining": round(self.fraction_remaining, 3),
            "threshold": self.threshold,
            "due": self.due.isoformat(),
            "breached": self.breached,
            "message": self.message(),
        }


@dataclass
class SupervisorReport:
    checked: int = 0
    escalations: list[Escalation] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    events: list[tuple[str, Event]] = field(default_factory=list)

    @property
    def breached(self) -> list[Escalation]:
        return [e for e in self.escalations if e.breached]

    def summary(self) -> str:
        if not self.escalations:
            return f"{self.checked} open case(s) checked; none at risk."
        return (
            f"{self.checked} open case(s) checked; {len(self.escalations)} at risk, "
            f"{len(self.breached)} already past due."
        )


def _threshold(pack: RulePack | None) -> float:
    return pack.breach_forecast_threshold if pack else 0.20


def watch(
    cases: Sequence[dict[str, Any]],
    ctx: Any,
    *,
    now: datetime | None = None,
) -> SupervisorReport:
    """Forecast every open case. Deterministic — no model is involved."""
    report = SupervisorReport()
    current = now or ctx.clock()

    for case in cases:
        status = str(case.get("status") or "")
        if status in TERMINAL:
            continue

        window = window_from_case(case, ctx.holidays)
        if window is None:
            report.skipped.append(str(case.get("case_ref") or case.get("id")))
            continue

        report.checked += 1
        category = str(case.get("category") or "")
        pack = ctx.packs.get(category)
        threshold = _threshold(pack)
        should, remaining = forecast_breach(window, threshold, current)
        if not should:
            continue

        escalation = Escalation(
            case_id=str(case.get("id")),
            case_ref=str(case.get("case_ref") or ""),
            status=status,
            urgency=str(case.get("urgency") or ""),
            category=category,
            fraction_remaining=remaining,
            due=window.due,
            threshold=threshold,
            breached=current > window.due,
        )
        report.escalations.append(escalation)
        report.events.append(
            (
                escalation.case_id,
                Event(
                    type="SLA_ESCALATION",
                    actor=ACTOR,
                    payload={
                        **escalation.as_payload(),
                        "citations": [
                            f"{category}.sla.breach_forecast_threshold = {threshold}",
                            f"{category}.sla.{escalation.urgency}.working_days = "
                            f"{window.working_days}",
                        ],
                    },
                ),
            )
        )

    return report


def run(cases: Sequence[dict[str, Any]], ctx: Any, *, now: datetime | None = None) -> SupervisorReport:
    """Forecast and record. Events are written through the same append-only chain."""
    report = watch(cases, ctx, now=now)
    if ctx.db is not None:
        for case_id, event in report.events:
            ctx.db.append_event(case_id, event.type, event.actor, event.payload)
    return report


# ─── Ops digest ─────────────────────────────────────────────────────────────


def digest(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Counts the Mission Control header renders. No PII, no model."""
    rows = list(cases)
    by_status: dict[str, int] = {}
    by_urgency: dict[str, int] = {}
    for case in rows:
        by_status[str(case.get("status"))] = by_status.get(str(case.get("status")), 0) + 1
        if case.get("urgency"):
            key = str(case["urgency"])
            by_urgency[key] = by_urgency.get(key, 0) + 1
    return {
        "total": len(rows),
        "open": sum(1 for c in rows if str(c.get("status")) not in TERMINAL),
        "by_status": by_status,
        "by_urgency": by_urgency,
        "actor": KERNEL,
    }
