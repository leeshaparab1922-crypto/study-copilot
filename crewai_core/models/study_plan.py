from enum import Enum

from pydantic import BaseModel


class EntryStatus(str, Enum):
    """Student-set progress on one StudyPlanEntry. Deliberately does NOT
    include a "missed" value — missed is never stored, only derived at
    read time from (date < today AND status still not_started/in_progress)
    by crewai_core/entry_status.py. Storing "missed" directly would let it
    go stale (a day marked missed today has no code forcing it to still
    read as missed tomorrow); deriving it removes that failure mode."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class StudyPlanEntry(BaseModel):
    subject: str
    topic_name: str
    hours_allocated: float
    status: EntryStatus = EntryStatus.NOT_STARTED


class DayPlan(BaseModel):
    date: str  # ISO format, e.g. "2026-07-06"
    entries: list[StudyPlanEntry]


class StudyPlan(BaseModel):
    days: list[DayPlan]
