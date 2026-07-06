from pydantic import BaseModel

from crewai_core.models.study_plan import DayPlan


class PlanRevision(BaseModel):
    """Output of the Plan Optimizer (Step 7, Section 2.2 #4): a PARTIAL
    day-wise plan covering only the remaining days (>= today) of the term —
    replaces those days in state.study_plan in place; days before today are
    left untouched."""

    days: list[DayPlan]
