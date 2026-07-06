"""Function-based guardrail for the (per-subject, per-topic) Assessment
Designer task.

Checks, for ONE on-demand quiz request for ONE (subject, topic) pair, against
that subject's SyllabusStructure (NOT the day-based study plan — a student
may request a quiz for any topic that subject's syllabus has, regardless of
what day the plan scheduled it for):
  1. The requested topic_name actually exists somewhere in that subject's
     SyllabusStructure (no inventing topics not in the syllabus).
  2. Every question's (subject, topic_name) pair matches exactly the
     requested subject and topic — no cross-subject or cross-topic leakage.
  3. The total question count is between 15 and 25 inclusive (flat cap,
     confirmed with user — question count itself is agent-decided within
     that range based on topic/sub-topic complexity, not tied to
     plan-allocated hours).
"""

from typing import Any

from crewai import TaskOutput

from crewai_core.models.quiz import QuizSet
from crewai_core.models.syllabus import SyllabusStructure

MIN_QUESTIONS = 15
MAX_QUESTIONS = 25


def make_assessment_guardrail(subject_name: str, topic_name: str, syllabus: SyllabusStructure):
    """Build a guardrail bound to one on-demand (subject, topic) request."""

    valid_topics = {
        topic.topic_name for unit in syllabus.units for topic in unit.topics
    }

    def guardrail(result: TaskOutput) -> tuple[bool, Any]:
        try:
            quiz = QuizSet.model_validate(
                result.pydantic if result.pydantic is not None else result.json_dict
            )
        except Exception as exc:
            return False, f"Output did not match QuizSet schema: {exc}"

        problems: list[str] = []

        if topic_name not in valid_topics:
            return False, (
                f"Requested topic '{topic_name}' does not exist anywhere in "
                f"{subject_name}'s syllabus — cannot generate a quiz for it."
            )

        for question in quiz.questions:
            if question.subject != subject_name:
                problems.append(
                    f"Question references subject '{question.subject}', but this "
                    f"request is scoped to {subject_name} only."
                )
            if question.topic_name != topic_name:
                problems.append(
                    f"Question references topic '{question.topic_name}', but this "
                    f"request is scoped to topic '{topic_name}' only — do not invent "
                    "or substitute a different topic."
                )

        question_count = len(quiz.questions)
        if question_count < MIN_QUESTIONS or question_count > MAX_QUESTIONS:
            problems.append(
                f"QuizSet has {question_count} questions — must be between "
                f"{MIN_QUESTIONS} and {MAX_QUESTIONS} inclusive."
            )

        if problems:
            return False, "; ".join(problems)

        return True, quiz

    return guardrail
