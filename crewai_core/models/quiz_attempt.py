from pydantic import BaseModel, Field


class QuestionAnswer(BaseModel):
    question_text: str
    selected_option_index: int
    correct: bool
    response_time_seconds: float
    retries: int  # times the student changed their answer before final submission


class QuizAttempt(BaseModel):
    """One whole-quiz submission (all questions from one QuizSet answered
    together), per decision confirmed with user (Step 6).

    attempted_at (Step 8, confirmed with user): ISO date string
    (YYYY-MM-DD), stamped by score_attempt() with real wall-clock
    date.today() at scoring time — the only real-world timestamp this
    project has for quiz activity, used by the Wellbeing Monitor to detect
    a gap in quiz activity (Section 2.3 #6)."""

    subject: str
    topic_name: str
    answers: list[QuestionAnswer] = Field(default_factory=list)
    attempted_at: str = ""

    @property
    def correct_count(self) -> int:
        return sum(1 for a in self.answers if a.correct)

    @property
    def total_questions(self) -> int:
        return len(self.answers)

    @property
    def accuracy(self) -> float:
        if self.total_questions == 0:
            return 0.0
        return self.correct_count / self.total_questions

    @property
    def passed(self) -> bool:
        """80%+ pass threshold — a label only, no retake/gating enforcement
        (decision #11 in 01-status-and-decisions.md)."""
        return self.accuracy >= 0.80
