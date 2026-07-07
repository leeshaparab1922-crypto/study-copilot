"""Step 8: Wellbeing Monitor (Section 2.3 #6). Plain, deterministic Python
— NOT a Crew/agent, per Section 2.3 and the project's ground rules.
Threshold-based detection ONLY — no sentiment/tone analysis or any claim
about emotional state (Section 4).

DEVIATION from Section 2.3 #6's literal input list ("usage timestamps, quiz
completion frequency, pace vs. plan"): given on-demand quizzes (deviation
#8) and the dropped pace concept (decision #13), the only real-world
timestamp this project has is QuizAttempt.attempted_at. "Completion
frequency" and "pace vs. plan" have no clean definition without a scheduled
cadence to compare against, so this checks ONLY days-since-last-activity —
confirmed with user (best-judgment call, given full discretion) rather than
inventing an undefined "frequency"/"pace" metric.

check_inactivity_flag(): flags when >= INACTIVITY_THRESHOLD_DAYS real
calendar days have passed since the most recent QuizAttempt anywhere in
quiz_history (any subject/topic) — confirmed with user, N=7.

check_missed_days_flag() (Task 5, day-plan-status feature — plan.md Open
Question 1): a SECOND, independent signal, added once StudyPlanEntry
gained a real status field (crewai_core/entry_status.py). Flags when the
student has MISSED_DAYS_THRESHOLD or more CONSECUTIVE scheduled days
missed (per entry_display_status()'s "missed" derivation), counting
backward from today. This does not replace check_inactivity_flag() — a
student can trigger either, both, or neither; StudyPlanFlow.check_wellbeing()
calls both and appends whatever flags result.
"""

from datetime import date, timedelta

from crewai_core.entry_status import entry_display_status
from crewai_core.models.quiz_attempt import QuizAttempt
from crewai_core.models.study_plan import StudyPlan
from crewai_core.models.wellbeing_flag import WellbeingFlag

INACTIVITY_THRESHOLD_DAYS = 7
MISSED_DAYS_THRESHOLD = 3


def check_inactivity_flag(
    quiz_history: list[QuizAttempt], today: str | None = None
) -> WellbeingFlag | None:
    """Returns a WellbeingFlag if the inactivity threshold is crossed, else
    None. today is an ISO date string override for testability; defaults to
    real wall-clock date.today()."""

    today_str = today if today is not None else date.today().isoformat()
    today_date = date.fromisoformat(today_str)

    if not quiz_history:
        return None

    most_recent = max(a.attempted_at for a in quiz_history if a.attempted_at)
    if not most_recent:
        return None

    days_since = (today_date - date.fromisoformat(most_recent)).days

    if days_since >= INACTIVITY_THRESHOLD_DAYS:
        return WellbeingFlag(
            reason=(
                f"No quiz activity recorded for {days_since} day(s) "
                f"(threshold: {INACTIVITY_THRESHOLD_DAYS}+ days) — flagged for "
                "human review, not a diagnosis of the student's state."
            ),
            flagged_at=today_str,
            days_since_last_activity=days_since,
        )

    return None


def _day_is_fully_missed(day_plan, today_str: str) -> bool:
    """A scheduled day counts as missed only if it has at least one entry
    AND every entry on it reads as "missed" — a day where the student
    completed some but not all of that day's entries is NOT counted as a
    missed day for the streak (per-entry granularity, not rolled up to an
    all-or-nothing day verdict; matches entry_status.py's per-entry design,
    see plan.md's per-entry-not-per-day architecture decision)."""

    if not day_plan.entries:
        return False
    return all(
        entry_display_status(day_plan.date, entry.status, today=today_str) == "missed"
        for entry in day_plan.entries
    )


def current_missed_day_streak(study_plan: StudyPlan | None, today: str | None = None) -> int:
    """The number of CONSECUTIVE scheduled days missed, counting backward
    from the most recent scheduled day that is strictly before today
    (entry_display_status() never marks today or future days as missed, so
    today itself is never part of the streak). A single fully-completed-
    or-in-progress day anywhere in that walk-back breaks the streak — this
    measures "how far behind is the student RIGHT NOW," not a lifetime
    count of every missed day ever. Returns 0 if study_plan is None/empty
    or there is no current streak.

    Shared by check_missed_days_flag() (below, the wellbeing threshold
    check) and PlanOptimizerCrew's missed_day_streak context (Task 6,
    crewai_core/flow.py's _maybe_trigger_plan_optimizer) — same underlying
    number, two different consumers."""

    if study_plan is None or not study_plan.days:
        return 0

    today_str = today if today is not None else date.today().isoformat()

    # Only days strictly before today are eligible to count as missed at
    # all (entry_display_status agrees), and only scheduled days (with at
    # least one entry) count toward the streak — walk backward from the
    # most recent such day.
    past_days = sorted(
        (d for d in study_plan.days if d.date < today_str and d.entries),
        key=lambda d: d.date,
        reverse=True,
    )

    streak = 0
    for day_plan in past_days:
        if _day_is_fully_missed(day_plan, today_str):
            streak += 1
        else:
            break

    return streak


def check_missed_days_flag(
    study_plan: StudyPlan | None, today: str | None = None
) -> WellbeingFlag | None:
    """Flags when the student has MISSED_DAYS_THRESHOLD or more CONSECUTIVE
    scheduled days missed (see current_missed_day_streak). Returns None if
    study_plan is None/empty, or if the current streak is below threshold."""

    today_str = today if today is not None else date.today().isoformat()
    streak = current_missed_day_streak(study_plan, today=today_str)

    if streak >= MISSED_DAYS_THRESHOLD:
        return WellbeingFlag(
            reason=(
                f"{streak} consecutive scheduled study day(s) missed "
                f"(threshold: {MISSED_DAYS_THRESHOLD}+ days) — flagged for "
                "human review, not a diagnosis of the student's state."
            ),
            flagged_at=today_str,
            days_since_last_activity=streak,
        )

    return None
