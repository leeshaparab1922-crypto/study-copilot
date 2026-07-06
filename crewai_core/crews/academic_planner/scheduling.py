"""Deterministic (non-LLM) day/hour budget allocator.

Splits the term's available study days across subjects, proportional to each
subject's share of total topics across all subjects, using a largest-remainder
proportional interleaving so a subject's assigned days are spread evenly
across the term rather than clumped at the start. On an assigned day, a
subject receives that entire day's available hours (no further splitting
with other subjects on the same day).

This exists so each per-subject Plan Generator LLM call receives a small,
already-conflict-free day/hour budget, instead of one LLM call trying to
place ~118 days x N subjects worth of entries in a single structured output
(which was empirically too large/slow — multi-minute calls with frequent
guardrail-triggered retries).
"""

from datetime import date, timedelta

from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.syllabus import SyllabusStructure

_WEEKDAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _available_hours_for_date(calendar: CalendarStructure, day: date) -> float:
    weekday_name = _WEEKDAY_NAMES[day.weekday()]

    for gap in calendar.personal_gaps:
        gap_start = date.fromisoformat(gap.start_date)
        gap_end = date.fromisoformat(gap.end_date)
        if gap_start <= day <= gap_end:
            return 0.0

    base_hours = getattr(calendar.weekly_available_hours, weekday_name)
    blocked_hours = sum(
        activity.hours_blocked
        for activity in calendar.recurring_activities
        if activity.day.lower() == weekday_name
    )
    return max(0.0, base_hours - blocked_hours)


def _term_days_with_hours(calendar: CalendarStructure) -> list[tuple[date, float]]:
    term_start = date.fromisoformat(calendar.term_start)
    term_end = date.fromisoformat(calendar.term_end)

    days = []
    current = term_start
    while current <= term_end:
        hours = _available_hours_for_date(calendar, current)
        if hours > 0:
            days.append((current, hours))
        current += timedelta(days=1)
    return days


def allocate_days_to_subjects(
    calendar: CalendarStructure, all_syllabi: list[SyllabusStructure]
) -> dict[str, list[tuple[str, float]]]:
    """Assign each term-day (with available hours > 0) to exactly one subject.

    Returns: {subject_name: [(iso_date, hours_available_that_day), ...]}

    Days are assigned proportional to each subject's share of total topics
    across all subjects, using largest-remainder-style proportional
    interleaving (each day goes to whichever subject is furthest behind its
    target share at that point), so a subject's days are spread evenly across
    the term rather than clumped together.
    """

    topic_counts = {
        syllabus.subject: sum(len(unit.topics) for unit in syllabus.units)
        for syllabus in all_syllabi
    }
    total_topics = sum(topic_counts.values())
    if total_topics == 0:
        return {subject: [] for subject in topic_counts}

    days_with_hours = _term_days_with_hours(calendar)
    total_days = len(days_with_hours)

    target_share = {
        subject: (count / total_topics) * total_days for subject, count in topic_counts.items()
    }
    assigned_count = {subject: 0 for subject in topic_counts}
    result: dict[str, list[tuple[str, float]]] = {subject: [] for subject in topic_counts}

    for day, hours in days_with_hours:
        # Assign this day to whichever subject is furthest behind its
        # proportional target share so far (largest-remainder interleaving).
        chosen_subject = max(
            topic_counts,
            key=lambda subject: target_share[subject] - assigned_count[subject],
        )
        result[chosen_subject].append((day.isoformat(), hours))
        assigned_count[chosen_subject] += 1

    return result
