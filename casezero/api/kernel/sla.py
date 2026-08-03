"""Malaysian working-day SLA arithmetic.

BNM expresses complaint deadlines in *working days*, so calendar arithmetic is
simply wrong: a High-urgency case opened Friday is due the following Friday, not
the following Wednesday. Getting this right is the difference between "11% of
deadlines missed" and zero.

Deterministic and LLM-free by design. Covered by api/tests/test_sla.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

# Malaysia has no DST; UTC+8 year round.
MYT = timezone(timedelta(hours=8))

# Federal public holidays. State holidays are deliberately excluded — a national
# complaints desk runs on the federal calendar.
#
# NOTE ON ISLAMIC DATES: Aidilfitri, Aidiladha, Awal Muharram, Maulidur Rasul and
# Nuzul Al-Quran depend on lunar observation and are gazetted each year. The dates
# below are the published 2026 estimates and are expected to be replaced with the
# gazetted list. Because they live in a table rather than in logic, correcting one
# is a data edit, not a code change.
MY_PUBLIC_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 1),    # New Year's Day
    date(2026, 2, 1),    # Federal Territory Day
    date(2026, 2, 17),   # Chinese New Year
    date(2026, 2, 18),   # Chinese New Year (2nd day)
    date(2026, 3, 6),    # Nuzul Al-Quran (estimated)
    date(2026, 3, 20),   # Hari Raya Aidilfitri (estimated)
    date(2026, 3, 21),   # Hari Raya Aidilfitri (2nd day, estimated)
    date(2026, 5, 1),    # Labour Day
    date(2026, 5, 27),   # Hari Raya Aidiladha (estimated)
    date(2026, 5, 31),   # Wesak Day
    date(2026, 6, 1),    # Agong's Birthday
    date(2026, 6, 16),   # Awal Muharram (estimated)
    date(2026, 8, 25),   # Maulidur Rasul (estimated)
    date(2026, 8, 31),   # Merdeka Day
    date(2026, 9, 16),   # Malaysia Day
    date(2026, 11, 8),   # Deepavali (estimated)
    date(2026, 12, 25),  # Christmas Day
}

# Cases that arrive after this hour start their clock on the next working day.
CUTOFF_HOUR = 17


def is_working_day(d: date, holidays: set[date] | None = None) -> bool:
    """Mon-Fri and not a gazetted public holiday."""
    if d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    return d not in (holidays if holidays is not None else MY_PUBLIC_HOLIDAYS_2026)


def next_working_day(d: date, holidays: set[date] | None = None) -> date:
    cursor = d + timedelta(days=1)
    while not is_working_day(cursor, holidays):
        cursor += timedelta(days=1)
    return cursor


def add_working_days(start: date, n: int, holidays: set[date] | None = None) -> date:
    """Return the date `n` working days after `start`.

    Day counting begins on the first working day strictly after `start`, which is
    how a complaints desk reads "within 5 working days of receipt".
    """
    if n < 0:
        raise ValueError("working days must be >= 0")
    cursor = start
    remaining = n
    while remaining > 0:
        cursor = next_working_day(cursor, holidays)
        remaining -= 1
    return cursor


def working_days_between(start: date, end: date, holidays: set[date] | None = None) -> int:
    """Count working days in (start, end]. Negative if end precedes start."""
    if end == start:
        return 0
    sign, lo, hi = (1, start, end) if end > start else (-1, end, start)
    count = 0
    cursor = lo
    while cursor < hi:
        cursor += timedelta(days=1)
        if is_working_day(cursor, holidays):
            count += 1
    return sign * count


@dataclass(frozen=True)
class SlaWindow:
    """A computed deadline plus everything the UI needs to render it honestly."""

    start: datetime
    due: datetime
    working_days: int
    #: One entry per calendar day from start to due — drives the SLA strip where
    #: weekends and holidays are visibly punched out rather than silently ignored.
    calendar: tuple[tuple[date, bool], ...]

    @property
    def due_date_display(self) -> str:
        return self.due.astimezone(MYT).strftime("%d %b %Y")


def compute_sla(
    received_at: datetime,
    working_days: int,
    holidays: set[date] | None = None,
) -> SlaWindow:
    """Compute the deadline for a case received at `received_at`.

    A complaint that lands after the cutoff, on a weekend, or on a holiday starts
    its clock on the next working day — the bank cannot be deemed to have received
    it while the desk is closed.
    """
    local = received_at.astimezone(MYT)
    clock_start_date = local.date()

    if not is_working_day(clock_start_date, holidays) or local.hour >= CUTOFF_HOUR:
        clock_start_date = next_working_day(clock_start_date, holidays)

    start = datetime.combine(clock_start_date, time(9, 0), tzinfo=MYT)
    due_date = add_working_days(clock_start_date, working_days, holidays)
    due = datetime.combine(due_date, time(17, 0), tzinfo=MYT)

    calendar: list[tuple[date, bool]] = []
    cursor = clock_start_date
    while cursor <= due_date:
        calendar.append((cursor, is_working_day(cursor, holidays)))
        cursor += timedelta(days=1)

    return SlaWindow(
        start=start,
        due=due,
        working_days=working_days,
        calendar=tuple(calendar),
    )


def fraction_remaining(window: SlaWindow, now: datetime | None = None) -> float:
    """Share of the working-day budget still available. Clamped to [0, 1].

    Measured in working days rather than wall-clock hours, because that is the
    unit the deadline itself is expressed in.
    """
    current = (now or datetime.now(timezone.utc)).astimezone(MYT)
    if window.working_days == 0:
        return 0.0
    used = working_days_between(window.start.date(), current.date())
    remaining = window.working_days - used
    return max(0.0, min(1.0, remaining / window.working_days))


def forecast_breach(
    window: SlaWindow,
    threshold: float = 0.20,
    now: datetime | None = None,
) -> tuple[bool, float]:
    """(should_escalate, fraction_remaining).

    The Supervisor agent escalates *before* the deadline is missed. Forecasting
    is the entire point: a watchdog that fires on breach has already failed.
    """
    remaining = fraction_remaining(window, now)
    return remaining <= threshold, remaining
