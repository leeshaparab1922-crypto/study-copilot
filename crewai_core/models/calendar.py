from pydantic import BaseModel


class CalendarEvent(BaseModel):
    name: str
    date: str  # ISO format YYYY-MM-DD


class WeeklyAvailableHours(BaseModel):
    monday: float
    tuesday: float
    wednesday: float
    thursday: float
    friday: float
    saturday: float
    sunday: float


class RecurringActivity(BaseModel):
    name: str
    day: str
    hours_blocked: float


class PersonalGap(BaseModel):
    reason: str
    start_date: str  # ISO format YYYY-MM-DD
    end_date: str  # ISO format YYYY-MM-DD


class CalendarStructure(BaseModel):
    term_start: str  # ISO format YYYY-MM-DD
    term_end: str  # ISO format YYYY-MM-DD
    exam_dates: list[CalendarEvent]
    assignment_deadlines: list[CalendarEvent]
    weekly_available_hours: WeeklyAvailableHours
    recurring_activities: list[RecurringActivity]
    personal_gaps: list[PersonalGap]
