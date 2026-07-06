"""Function-based hallucination guardrail for the Syllabus Analyst task.

CrewAI's built-in HallucinationGuardrail (crewai.tasks.hallucination_guardrail)
is a CrewAI Enterprise-only feature and is not available in open-source CrewAI.
This module is the open-source substitute described in Section 3.1 of the
build prompt: a function-based guardrail that checks every unit/topic/
sub_topic string emitted by the agent against the subject's raw input
syllabus text (the source of truth), rejecting the output if anything was
invented.
"""

from typing import Any

from crewai import TaskOutput

from crewai_core.models.syllabus import SyllabusStructure


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def make_syllabus_hallucination_guardrail(raw_syllabus_text: str):
    """Build a guardrail bound to one subject's raw syllabus source text."""

    normalized_source = _normalize(raw_syllabus_text)

    def guardrail(result: TaskOutput) -> tuple[bool, Any]:
        try:
            structure = SyllabusStructure.model_validate(
                result.pydantic if result.pydantic is not None else result.json_dict
            )
        except Exception as exc:
            return False, f"Output did not match SyllabusStructure schema: {exc}"

        invented: list[str] = []
        for unit in structure.units:
            if _normalize(unit.unit_name) not in normalized_source:
                invented.append(f"unit '{unit.unit_name}'")
            for topic in unit.topics:
                if _normalize(topic.topic_name) not in normalized_source:
                    invented.append(f"topic '{topic.topic_name}'")
                for sub_topic in topic.sub_topics:
                    if _normalize(sub_topic) not in normalized_source:
                        invented.append(f"sub_topic '{sub_topic}'")

        if invented:
            return False, (
                "Output contains items not present in the source syllabus text: "
                + "; ".join(invented)
                + ". Remove or correct these — do not invent syllabus content."
            )

        return True, structure

    return guardrail
