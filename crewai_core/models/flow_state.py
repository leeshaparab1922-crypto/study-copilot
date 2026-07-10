from pydantic import Field

from crewai.flow.flow import FlowState
from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.quiz_attempt import QuizAttempt
from crewai_core.models.study_plan import StudyPlan
from crewai_core.models.syllabus import SyllabusStructure
from crewai_core.models.weak_topic import WeakTopicUpdate
from crewai_core.models.wellbeing_flag import WellbeingFlag


class StudyPlanFlowState(FlowState):
    """Per-student Flow state (Section 2.1). One Flow instance per student.

    Inherits from crewai's FlowState (not plain pydantic BaseModel) to gain
    a real `id: str` field with the same default_factory semantics CrewAI's
    own Flow machinery expects. StudyPlanFlow's __init__ (crewai_core/flow.py)
    always sets this id explicitly via crewai_core/flow_id.py's
    derive_flow_id(student_id) — deterministic, so the same student_id
    always maps to the same persisted SQLite flow_uuid.

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
