from uuid import uuid4

from pydantic import BaseModel, Field


class WellbeingFlag(BaseModel):
    """Step 8 (Section 2.3 #6): a threshold-based disengagement signal,
    NOT a diagnosis or emotional-state claim (Section 4 explicitly excludes
    sentiment/tone analysis). Appended to state.wellbeing_flags. Reaching a
    real person's judgment is now asynchronous: the flag is recorded
    immediately and acknowledged later via a separate call
    (StudyPlanFlow.acknowledge_wellbeing_flag), rather than a synchronous
    console pause."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    reason: str
    flagged_at: str  # ISO date string (YYYY-MM-DD), real wall-clock date.today()
    days_since_last_activity: int | None = None  # None if there has never been any attempt
    acknowledged: bool = False
    reviewer_note: str | None = None
