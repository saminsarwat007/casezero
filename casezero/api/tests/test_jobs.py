from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.agents.base import AgentContext
from api.jobs import run_supervisor_once


def _at_risk_case(fake_db, now: datetime) -> dict:
    return fake_db.create_case(
        status="REVIEW_PENDING",
        category="unauthorized_transaction",
        urgency="High",
        sla_start=(now - timedelta(days=10)).isoformat(),
        sla_due=(now + timedelta(hours=2)).isoformat(),
        sla_working_days=5,
    )


def test_scheduler_records_once_per_forecast_day(fake_db):
    now = datetime(2026, 8, 4, 2, 0, tzinfo=timezone.utc)
    case = _at_risk_case(fake_db, now)
    ctx = AgentContext(db=fake_db, now=now)

    first = run_supervisor_once(db=fake_db, context=ctx, now=now)
    second = run_supervisor_once(db=fake_db, context=ctx, now=now)

    assert first.at_risk == first.recorded == 1
    assert second.recorded == 0
    assert second.duplicates == 1
    events = fake_db.get_events(case["id"])
    assert events[-1].payload["forecast_date"] == "2026-08-04"


def test_new_breach_state_is_recorded_on_same_day(fake_db):
    now = datetime(2026, 8, 4, 2, 0, tzinfo=timezone.utc)
    case = _at_risk_case(fake_db, now)
    ctx = AgentContext(db=fake_db, now=now)
    run_supervisor_once(db=fake_db, context=ctx, now=now)

    later = now + timedelta(hours=4)
    result = run_supervisor_once(db=fake_db, context=ctx, now=later)

    assert result.breached == 1
    assert result.recorded == 1
    assert len(fake_db.get_events(case["id"])) == 2
