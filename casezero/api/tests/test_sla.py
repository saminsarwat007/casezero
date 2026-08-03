"""Working-day SLA arithmetic.

These assertions are the difference between "11% of regulatory deadlines missed"
and zero, so each one encodes a rule a BNM examiner would actually check.
"""

from datetime import date, datetime, timedelta

from api.kernel.sla import (
    MYT,
    add_working_days,
    compute_sla,
    forecast_breach,
    fraction_remaining,
    is_working_day,
    next_working_day,
    working_days_between,
)


def at(y: int, m: int, d: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(y, m, d, hour, minute, tzinfo=MYT)


class TestWorkingDayBasics:
    def test_weekends_are_not_working_days(self):
        assert not is_working_day(date(2026, 8, 8))   # Saturday
        assert not is_working_day(date(2026, 8, 9))   # Sunday
        assert is_working_day(date(2026, 8, 10))      # Monday

    def test_gazetted_holiday_is_not_a_working_day(self):
        assert not is_working_day(date(2026, 8, 31))  # Merdeka Day, a Monday
        assert not is_working_day(date(2026, 9, 16))  # Malaysia Day

    def test_next_working_day_skips_the_weekend(self):
        assert next_working_day(date(2026, 8, 7)) == date(2026, 8, 10)

    def test_next_working_day_skips_a_holiday_landing_on_a_monday(self):
        # Friday 28 Aug -> Monday 31 Aug is Merdeka -> Tuesday 1 Sep.
        assert next_working_day(date(2026, 8, 28)) == date(2026, 9, 1)


class TestFridayIsTheWholePoint:
    """The single most valuable test in the suite.

    A High-urgency complaint carries a 5-working-day deadline. Naive calendar
    arithmetic makes that Wednesday and silently breaches the BNM deadline by two
    days. Correct arithmetic makes it the following Friday.
    """

    def test_high_urgency_friday_intake_is_due_the_following_friday(self):
        window = compute_sla(at(2026, 8, 7), working_days=5)  # Friday
        assert window.due.date() == date(2026, 8, 14)         # following Friday
        naive = at(2026, 8, 7) + timedelta(days=5)
        assert naive.date() == date(2026, 8, 12)             # what a bug would give
        assert window.due.date() != naive.date()

    def test_add_working_days_matches(self):
        assert add_working_days(date(2026, 8, 7), 5) == date(2026, 8, 14)


class TestClockStart:
    def test_weekend_arrival_starts_monday(self):
        window = compute_sla(at(2026, 8, 8), working_days=5)  # Saturday
        assert window.start.date() == date(2026, 8, 10)
        assert window.due.date() == date(2026, 8, 17)

    def test_after_hours_arrival_starts_next_working_day(self):
        # 18:00 Friday: the desk is closed, so receipt cannot be deemed Friday.
        window = compute_sla(at(2026, 8, 7, hour=18), working_days=5)
        assert window.start.date() == date(2026, 8, 10)
        assert window.due.date() == date(2026, 8, 17)

    def test_holiday_arrival_starts_next_working_day(self):
        window = compute_sla(at(2026, 8, 31), working_days=5)  # Merdeka
        assert window.start.date() == date(2026, 9, 1)

    def test_deadline_spanning_a_holiday_is_pushed_out(self):
        # Thursday 27 Aug + 5 WD, with Merdeka (Mon 31 Aug) removed.
        window = compute_sla(at(2026, 8, 27), working_days=5)
        assert window.due.date() == date(2026, 9, 4)


class TestUrgencyTiers:
    """High: 5 WD. Medium: 20 WD. Low: 20 WD + extensions. Straight from the brief."""

    def test_medium_and_low_are_twenty_working_days(self):
        for days in (20, 20):
            window = compute_sla(at(2026, 8, 3), working_days=days)  # Monday
            assert window.working_days == days
            assert working_days_between(window.start.date(), window.due.date()) == days

    def test_low_urgency_deadline_is_much_later_than_high(self):
        high = compute_sla(at(2026, 8, 3), working_days=5)
        low = compute_sla(at(2026, 8, 3), working_days=20)
        assert low.due > high.due


class TestCalendarStrip:
    """The SLA strip renders weekends as punched-out gaps rather than hiding them."""

    def test_strip_marks_non_working_days(self):
        window = compute_sla(at(2026, 8, 7), working_days=5)
        days = dict(window.calendar)
        assert days[date(2026, 8, 8)] is False   # Saturday
        assert days[date(2026, 8, 9)] is False   # Sunday
        assert days[date(2026, 8, 10)] is True   # Monday

    def test_strip_covers_start_through_due(self):
        window = compute_sla(at(2026, 8, 7), working_days=5)
        assert window.calendar[0][0] == window.start.date()
        assert window.calendar[-1][0] == window.due.date()


class TestBreachForecast:
    """A watchdog that fires on breach has already failed. It must forecast."""

    def test_full_window_remaining_at_intake(self):
        window = compute_sla(at(2026, 8, 3), working_days=5)
        assert fraction_remaining(window, now=at(2026, 8, 3)) == 1.0

    def test_escalates_once_under_twenty_percent(self):
        window = compute_sla(at(2026, 8, 3), working_days=5)  # due Mon 10 Aug
        # Four working days consumed by Friday: 1/5 = 20% left, at the threshold.
        should_escalate, remaining = forecast_breach(window, now=at(2026, 8, 7))
        assert should_escalate
        assert remaining <= 0.20

    def test_does_not_escalate_early(self):
        window = compute_sla(at(2026, 8, 3), working_days=20)
        should_escalate, remaining = forecast_breach(window, now=at(2026, 8, 5))
        assert not should_escalate
        assert remaining > 0.20

    def test_never_reports_negative_remaining(self):
        window = compute_sla(at(2026, 8, 3), working_days=5)
        _, remaining = forecast_breach(window, now=at(2026, 9, 30))
        assert remaining == 0.0

    def test_weekend_does_not_consume_the_budget(self):
        window = compute_sla(at(2026, 8, 3), working_days=5)
        friday = fraction_remaining(window, now=at(2026, 8, 7))
        sunday = fraction_remaining(window, now=at(2026, 8, 9))
        assert friday == sunday


class TestDisplay:
    def test_due_date_renders_for_the_mandatory_disclosure(self):
        # BNM_TIMELINE requires an actual date in the customer email, not a duration.
        window = compute_sla(at(2026, 8, 7), working_days=5)
        assert window.due_date_display == "14 Aug 2026"
