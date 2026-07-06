from enum import Enum

from pydantic import BaseModel


class TopicStatus(str, Enum):
    NOT_STARTED = "Not Started"
    STRUGGLING = "Struggling"
    IMPROVING = "Improving"
    MASTERED = "Mastered"


class WeakTopicUpdate(BaseModel):
    """Rollup status for one (subject, topic) pair, over the last N=5
    attempts for that pair (Section 2.3; thresholds confirmed with user —
    see decisions #8 and (rollup cutoffs) in 01-status-and-decisions.md)."""

    subject: str
    topic_name: str
    status: TopicStatus
    attempts_considered: int  # how many of the last N attempts were actually available (<=5)
    accuracy: float  # accuracy over attempts_considered
