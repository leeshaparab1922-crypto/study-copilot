"""Pytest coverage for wellbeing_monitor.py's threshold logic — no LLM
call, pure functions, same style as crewai_core/test_entry_status.py.

check_missed_days_flag() cases (Task 5): 0 missed days -> None; exactly
threshold-1 consecutive missed days -> None; exactly threshold -> flagged;
threshold+ -> flagged; a completed day breaking up an otherwise-missed
streak correctly resets the count (realistic mixed sequence, not just a
boundary case).

Run with: uv run pytest crewai_core/test_wellbeing_monitor.py
"""

from crewai_core.models.study_plan import DayPlan, EntryStatus, StudyPlan, StudyPlanEntry
from crewai_core.wellbeing_monitor import MISSED_DAYS_THRESHOLD, check_missed_days_flag

TODAY = "2026-07-15"


def _day(date: str, status: EntryStatus = EntryStatus.NOT_STARTED, entries=None) -> DayPlan:
    if entries is not None:
        return DayPlan(date=date, entries=entries)
    return DayPlan(
        date=date,
        entries=[StudyPlanEntry(subject="Mathematics", topic_name="Polynomials", hours_allocated=1.0, status=status)],
    )


def test_no_study_plan_returns_none():
    assert check_missed_days_flag(None, today=TODAY) is None


def test_empty_study_plan_returns_none():
    assert check_missed_days_flag(StudyPlan(days=[]), today=TODAY) is None


def test_zero_missed_days_returns_none():
    # Only a completed day yesterday — no missed streak at all.
    plan = StudyPlan(days=[_day("2026-07-14", EntryStatus.COMPLETED)])
    assert check_missed_days_flag(plan, today=TODAY) is None


def test_below_threshold_returns_none():
    # threshold - 1 consecutive missed days.
    dates = ["2026-07-12", "2026-07-13", "2026-07-14"][: MISSED_DAYS_THRESHOLD - 1]
    plan = StudyPlan(days=[_day(d, EntryStatus.NOT_STARTED) for d in dates])
    assert check_missed_days_flag(plan, today=TODAY) is None


def test_exactly_threshold_flags():
    dates = [f"2026-07-{12 + i}" for i in range(MISSED_DAYS_THRESHOLD)]
    plan = StudyPlan(days=[_day(d, EntryStatus.NOT_STARTED) for d in dates])
    flag = check_missed_days_flag(plan, today=TODAY)
    assert flag is not None
    assert flag.days_since_last_activity == MISSED_DAYS_THRESHOLD
    assert str(MISSED_DAYS_THRESHOLD) in flag.reason


def test_above_threshold_flags():
    dates = [f"2026-07-{10 + i}" for i in range(MISSED_DAYS_THRESHOLD + 2)]
    plan = StudyPlan(days=[_day(d, EntryStatus.NOT_STARTED) for d in dates])
    flag = check_missed_days_flag(plan, today=TODAY)
    assert flag is not None
    assert flag.days_since_last_activity == MISSED_DAYS_THRESHOLD + 2


def test_completed_day_breaks_streak_realistic_mixed_sequence():
    # missed, missed, completed, missed, missed — walking backward from
    # today, the streak must stop at the completed day (2026-07-13), not
    # continue past it, even though there ARE more missed days earlier.
    plan = StudyPlan(
        days=[
            _day("2026-07-10", EntryStatus.NOT_STARTED),  # missed (older, beyond the break)
            _day("2026-07-11", EntryStatus.NOT_STARTED),  # missed (older, beyond the break)
            _day("2026-07-13", EntryStatus.COMPLETED),    # breaks the streak
            _day("2026-07-14", EntryStatus.NOT_STARTED),  # missed (most recent, part of current streak)
        ]
    )
    # Only 1 day in the current streak (07-14) since 07-13 was completed.
    assert check_missed_days_flag(plan, today=TODAY) is None


def test_partial_day_completion_not_counted_as_missed():
    # A day with ONE entry completed and ONE still not_started is NOT a
    # fully-missed day (per-entry granularity, not all-or-nothing).
    mixed_entries = [
        StudyPlanEntry(subject="Mathematics", topic_name="Polynomials", hours_allocated=1.0, status=EntryStatus.COMPLETED),
        StudyPlanEntry(subject="Physics", topic_name="Motion", hours_allocated=1.0, status=EntryStatus.NOT_STARTED),
    ]
    dates_before = [f"2026-07-{10 + i}" for i in range(MISSED_DAYS_THRESHOLD)]
    plan = StudyPlan(
        days=[_day(d, EntryStatus.NOT_STARTED) for d in dates_before]
        + [_day("2026-07-14", entries=mixed_entries)]
    )
    # The mixed day breaks the streak counted from today backward.
    assert check_missed_days_flag(plan, today=TODAY) is None


def test_today_and_future_days_never_count_as_missed():
    # Days >= today are never eligible, per entry_display_status().
    plan = StudyPlan(
        days=[
            _day(TODAY, EntryStatus.NOT_STARTED),
            _day("2026-07-20", EntryStatus.NOT_STARTED),
        ]
    )
    assert check_missed_days_flag(plan, today=TODAY) is None


def test_day_with_no_entries_does_not_crash_and_is_not_counted():
    plan = StudyPlan(
        days=[
            _day("2026-07-12", entries=[]),
            _day("2026-07-13", EntryStatus.NOT_STARTED),
            _day("2026-07-14", EntryStatus.NOT_STARTED),
        ]
    )
    # Empty-entries day is skipped, not counted as missed and not breaking
    # the streak either — only 2 real missed days here, below threshold 3.
    assert check_missed_days_flag(plan, today=TODAY) is None
