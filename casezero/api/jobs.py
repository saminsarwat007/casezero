"""Production scheduler for the deterministic SLA supervisor.

Run one dedicated worker per deployment::

    .venv/bin/python -m api.jobs

The scheduler deliberately does not start inside FastAPI: multiple web workers
would otherwise write duplicate escalations. ``--once`` is the deploy smoke and
cron-friendly mode.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from apscheduler.schedulers.blocking import BlockingScheduler

from api.agents.base import AgentContext
from api.agents.supervisor import Escalation, watch
from api.config import Settings, get_settings
from api.db.client import Database, get_db
from api.kernel.chain import ChainEvent
from api.kernel.sla import MYT


@dataclass(frozen=True)
class JobResult:
    checked: int
    at_risk: int
    breached: int
    recorded: int
    duplicates: int

    def summary(self) -> str:
        return (
            f"checked={self.checked} at_risk={self.at_risk} "
            f"breached={self.breached} recorded={self.recorded} "
            f"duplicates={self.duplicates}"
        )


def _already_recorded(
    events: Sequence[ChainEvent],
    escalation: Escalation,
    now: datetime,
) -> bool:
    """One forecast per case/day/state; a newly breached case gets a new event."""
    day = now.astimezone(MYT).date().isoformat()
    for event in reversed(events):
        if event.event_type != "SLA_ESCALATION":
            continue
        payload = event.payload
        if (
            payload.get("forecast_date") == day
            and bool(payload.get("breached")) == escalation.breached
        ):
            return True
    return False


def run_supervisor_once(
    *,
    db: Any | None = None,
    context: AgentContext | None = None,
    now: datetime | None = None,
) -> JobResult:
    """Forecast open cases and append only non-duplicate escalation links."""
    repository = db or get_db()
    ctx = context or AgentContext(db=repository)
    current = now or datetime.now(timezone.utc)
    report = watch(repository.list_cases(limit=2000), ctx, now=current)
    recorded = 0
    duplicates = 0

    by_id = {escalation.case_id: escalation for escalation in report.escalations}
    for case_id, event in report.events:
        escalation = by_id[case_id]
        existing = repository.get_events(case_id)
        if _already_recorded(existing, escalation, current):
            duplicates += 1
            continue
        payload = {
            **event.payload,
            "forecast_date": current.astimezone(MYT).date().isoformat(),
        }
        repository.append_event(case_id, event.type, event.actor, payload)
        recorded += 1

    return JobResult(
        checked=report.checked,
        at_risk=len(report.escalations),
        breached=len(report.breached),
        recorded=recorded,
        duplicates=duplicates,
    )


def run_scheduler(settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    scheduler = BlockingScheduler(timezone=MYT)
    scheduler.add_job(
        run_supervisor_once,
        "interval",
        minutes=cfg.supervisor_interval_minutes,
        id="casezero-sla-supervisor",
        coalesce=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),
    )
    print(
        "CaseZero SLA supervisor started; interval="
        f"{cfg.supervisor_interval_minutes} minute(s)."
    )
    scheduler.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="CaseZero SLA supervisor worker")
    parser.add_argument("--once", action="store_true", help="Run one forecast and exit")
    args = parser.parse_args()
    if args.once:
        print(run_supervisor_once().summary())
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
