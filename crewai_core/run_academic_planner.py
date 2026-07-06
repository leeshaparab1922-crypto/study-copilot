"""Manual runner: runs the Syllabus Analyst Crew across all sample subjects
CONCURRENTLY, parses the sample calendar via the Academic Planner Crew,
computes a deterministic per-subject day/hour budget (scheduling.py), then
runs the Plan Generator Crew once per subject CONCURRENTLY and merges the
results into one StudyPlan spanning all subjects.

Usage:
    uv run python -m crewai_core.run_academic_planner
"""

import sys

if sys.stdout.encoding.lower() != "utf-8":
    # Windows cp1252 console can't print CrewAI's UTF-8 log output (box-drawing chars, etc.)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from crewai_core.crews.academic_planner.crew import AcademicPlannerCrew
from crewai_core.crews.academic_planner.scheduling import allocate_days_to_subjects
from crewai_core.crews.plan_generator.crew import PlanGeneratorCrew
from crewai_core.crews.syllabus_analyst.crew import SyllabusAnalystCrew
from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.study_plan import DayPlan, StudyPlan
from crewai_core.models.syllabus import SyllabusStructure

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def merge_subject_plans(subject_plans: list[StudyPlan]) -> StudyPlan:
    """Union each subject's DayPlan.entries onto the same date, since the
    scheduling budget guarantees no two subjects were ever assigned
    overlapping hours on the same day."""

    entries_by_date: dict[str, list] = {}
    for plan in subject_plans:
        for day_plan in plan.days:
            entries_by_date.setdefault(day_plan.date, []).extend(day_plan.entries)

    merged_days = [
        DayPlan(date=day, entries=entries) for day, entries in sorted(entries_by_date.items())
    ]
    return StudyPlan(days=merged_days)


async def analyze_subject(subject_entry: dict) -> SyllabusStructure:
    print(f"=== Starting syllabus analysis: {subject_entry['subject']} ===")
    crew_instance = SyllabusAnalystCrew(raw_syllabus=subject_entry)
    output = await crew_instance.crew().kickoff_async(
        inputs={"raw_syllabus_json": crew_instance.raw_syllabus_text}
    )
    print(f"=== Finished syllabus analysis: {subject_entry['subject']} ===")
    return output.pydantic


async def generate_subject_plan(
    subject_syllabus: SyllabusStructure,
    day_budget: list[tuple[str, float]],
    calendar: CalendarStructure,
) -> StudyPlan:
    print(f"=== Starting plan generation: {subject_syllabus.subject} ===")
    plan_crew = PlanGeneratorCrew(
        subject_syllabus=subject_syllabus, day_budget=day_budget, calendar=calendar
    )
    result = await plan_crew.crew().kickoff_async(
        inputs={
            "subject_name": plan_crew.subject_name,
            "subject_syllabus_json": plan_crew.subject_syllabus_text,
            "day_budget_json": plan_crew.day_budget_text,
            "exams_and_deadlines_json": plan_crew.exams_and_deadlines_text,
        }
    )
    print(f"=== Finished plan generation: {subject_syllabus.subject} ===")
    return result.pydantic


async def run_pipeline(syllabi: list[dict], raw_calendar: dict) -> StudyPlan:
    all_syllabi = list(
        await asyncio.gather(*(analyze_subject(entry) for entry in syllabi))
    )
    print(f"\nDone analyzing {len(all_syllabi)} subjects. Parsing calendar...\n")

    planner_crew = AcademicPlannerCrew(raw_calendar=raw_calendar)
    calendar_result = await planner_crew.crew().kickoff_async(
        inputs={"raw_calendar_json": planner_crew.raw_calendar_text}
    )
    calendar = calendar_result.pydantic

    print("\n=== CalendarStructure ===")
    print(calendar.model_dump_json(indent=2))

    print("\nComputing per-subject day/hour budget...")
    budget = allocate_days_to_subjects(calendar, all_syllabi)
    for subject, days in budget.items():
        print(f"  {subject}: {len(days)} days, {sum(h for _, h in days):.1f}h total")

    subject_plans = list(
        await asyncio.gather(
            *(
                generate_subject_plan(subject_syllabus, budget[subject_syllabus.subject], calendar)
                for subject_syllabus in all_syllabi
            )
        )
    )

    print("\nMerging per-subject plans into one StudyPlan...")
    return merge_subject_plans(subject_plans)


def main() -> None:
    with open(FIXTURES_DIR / "sample_syllabi.json", encoding="utf-8") as f:
        syllabi = json.load(f)

    with open(FIXTURES_DIR / "sample_calendar.json", encoding="utf-8") as f:
        raw_calendar = json.load(f)

    study_plan = asyncio.run(run_pipeline(syllabi, raw_calendar))

    print(f"\n=== Merged StudyPlan ({len(study_plan.days)} days) ===")
    print(study_plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
