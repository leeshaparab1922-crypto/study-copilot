"""Derived display status for one StudyPlanEntry. Plain, deterministic
Python — NOT a Crew/agent, same category as performance_tracker.py and
wellbeing_monitor.py.

"missed" is never stored on StudyPlanEntry.status (see EntryStatus in
crewai_core/models/study_plan.py) — it is computed here, at read time,
from (day_date < today AND the entry's stored status is still
not_started/in_progress). Storing "missed" directly would let it go stale
(a day marked missed today has no code forcing it to still read as missed
tomorrow, or forcing it back off if a caller later completes it); deriving
it removes that whole class of bug.

entry_display_status() returns a plain str, not EntryStatus, since "missed"
is not (and must not become) a member of that enum.
"""

from datetime import date

from crewai_core.models.study_plan import EntryStatus

MISSABLE_STATUSES = (EntryStatus.NOT_STARTED, EntryStatus.IN_PROGRESS)


def entry_display_status(
    day_date: str, entry_status: EntryStatus, today: str | None = None
) -> str:
    """today is an ISO date string override for testability; defaults to
    real wall-clock date.today() (same convention as
    wellbeing_monitor.check_inactivity_flag's today parameter).

    Only a STRICTLY past day_date (day_date < today) can ever read as
    missed — today's and future entries stay as their stored status
    regardless of value, since the student still has time to act on them.
    """

    today_str = today if today is not None else date.today().isoformat()

    if day_date < today_str and entry_status in MISSABLE_STATUSES:
        return "missed"

    return entry_status.value
