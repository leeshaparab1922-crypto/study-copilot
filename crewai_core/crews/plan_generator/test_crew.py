"""Evaluate the (per-subject) Plan Generator Crew via CrewAI's built-in
test/eval harness (Crew.test), per Section 3.6 of the build prompt.

Tests against the first subject (Mathematics) using a day/hour budget
computed from the sample calendar and all 6 sample subjects, so the budget
looks like what a real run would produce.

Usage:
    uv run python -m crewai_core.crews.plan_generator.test_crew [n_iterations]
"""

import json
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from crewai_core.crews.academic_planner.scheduling import allocate_days_to_subjects
from crewai_core.crews.plan_generator.crew import PlanGeneratorCrew
from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.syllabus import SyllabusStructure

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def main() -> None:
    n_iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 2

    with open(FIXTURES_DIR / "sample_calendar.json", encoding="utf-8") as f:
        raw_calendar = json.load(f)
    with open(FIXTURES_DIR / "sample_syllabi.json", encoding="utf-8") as f:
        raw_syllabi = json.load(f)

    calendar = CalendarStructure.model_validate(raw_calendar)
    all_syllabi = [SyllabusStructure.model_validate(entry) for entry in raw_syllabi]

    budget = allocate_days_to_subjects(calendar, all_syllabi)

    subject_syllabus = all_syllabi[0]  # Mathematics
    subject_budget = budget[subject_syllabus.subject]

    crew_instance = PlanGeneratorCrew(
        subject_syllabus=subject_syllabus, day_budget=subject_budget, calendar=calendar
    )

    print(
        f"Testing PlanGeneratorCrew on '{subject_syllabus.subject}' "
        f"({len(subject_budget)} budgeted days) for {n_iterations} iterations..."
    )
    crew_instance.crew().test(
        n_iterations=n_iterations,
        eval_llm="gpt-4o-mini",
        inputs={
            "subject_name": crew_instance.subject_name,
            "subject_syllabus_json": crew_instance.subject_syllabus_text,
            "day_budget_json": crew_instance.day_budget_text,
            "exams_and_deadlines_json": crew_instance.exams_and_deadlines_text,
        },
    )


if __name__ == "__main__":
    main()
