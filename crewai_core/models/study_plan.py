from pydantic import BaseModel


class StudyPlanEntry(BaseModel):
    subject: str
    topic_name: str
    hours_allocated: float


class DayPlan(BaseModel):
    date: str  # ISO format, e.g. "2026-07-06"
    entries: list[StudyPlanEntry]


class StudyPlan(BaseModel):
    days: list[DayPlan]
