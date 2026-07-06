from pydantic import BaseModel, Field

from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.quiz_attempt import QuizAttempt
from crewai_core.models.study_plan import StudyPlan
from crewai_core.models.syllabus import SyllabusStructure
from crewai_core.models.weak_topic import WeakTopicUpdate
from crewai_core.models.wellbeing_flag import WellbeingFlag


class StudyPlanFlowState(BaseModel):
    """Per-student Flow state (Section 2.1). One Flow instance per student.

    quiz_history, weak_topics, and wellbeing_flags are all typed now
    (Steps 6 and 8) — QuizAttempt, WeakTopicUpdate, and WellbeingFlag
    respectively. No more list[dict] placeholders.
    """

    student_id: str = ""
    grade: str = ""

    syllabi: list[SyllabusStructure] = Field(default_factory=list)
    calendar: CalendarStructure | None = None
    study_plan: StudyPlan | None = None

    quiz_history: list[QuizAttempt] = Field(default_factory=list)
    weak_topics: list[WeakTopicUpdate] = Field(default_factory=list)
    wellbeing_flags: list[WellbeingFlag] = Field(default_factory=list)
