"""Evaluate the (per-subject, per-topic) Assessment Designer Crew via
CrewAI's built-in test/eval harness (Crew.test), per Section 3.6 of the
build prompt.

Tests an on-demand quiz request for Mathematics / a real topic from the
sample syllabus, so the guardrail's syllabus-membership scoping looks like
what a real student-requested quiz would produce.

Usage:
    uv run python -m crewai_core.crews.assessment_designer.test_crew [n_iterations]
"""

import json
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import asyncio

from dotenv import load_dotenv

load_dotenv()

from crewai_core.crews.assessment_designer.crew import AssessmentDesignerCrew
from crewai_core.crews.syllabus_analyst.crew import SyllabusAnalystCrew
from crewai_core.models.syllabus import SyllabusStructure

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


async def _build_sample_syllabus() -> SyllabusStructure:
    """Runs the real Step 2 pipeline for just Mathematics, to get one real
    SyllabusStructure to test the Assessment Designer against."""
    with open(FIXTURES_DIR / "sample_syllabi.json", encoding="utf-8") as f:
        raw_syllabi = json.load(f)

    mathematics_entry = next(e for e in raw_syllabi if e["subject"] == "Mathematics")
    crew_instance = SyllabusAnalystCrew(raw_syllabus=mathematics_entry)
    output = await crew_instance.crew().kickoff_async(
        inputs={"raw_syllabus_json": crew_instance.raw_syllabus_text}
    )
    return output.pydantic


def main() -> None:
    n_iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 2

    syllabus = asyncio.run(_build_sample_syllabus())
    subject_name = syllabus.subject
    topic_name = syllabus.units[0].topics[0].topic_name

    crew_instance = AssessmentDesignerCrew(
        subject_name=subject_name, topic_name=topic_name, syllabus=syllabus
    )

    print(
        f"Testing AssessmentDesignerCrew on-demand quiz for '{subject_name}' / "
        f"'{topic_name}' for {n_iterations} iterations..."
    )
    crew_instance.crew().test(
        n_iterations=n_iterations,
        eval_llm="gpt-4o-mini",
        inputs={
            "subject_name": crew_instance.subject_name,
            "topic_name": crew_instance.topic_name,
            "subject_syllabus_json": syllabus.model_dump_json(),
        },
    )


if __name__ == "__main__":
    main()
