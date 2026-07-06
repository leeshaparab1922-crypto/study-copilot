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
"""

from datetime import date

from crewai_core.models.quiz_attempt import QuizAttempt
from crewai_core.models.wellbeing_flag import WellbeingFlag

INACTIVITY_THRESHOLD_DAYS = 7


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
