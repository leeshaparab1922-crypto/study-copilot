"""Evaluate the PlanOptimizerCrew via CrewAI's built-in test/eval harness
(Crew.test), per Section 3.6 of the build prompt.

Builds a real remaining-days slice + weak-topic state (one Struggling topic,
one Mastered topic) from the sample fixtures via the real Step 2-4 pipeline,
so the Crew is tested against realistic input, not hand-typed stub data.

Usage:
    uv run python -m crewai_core.crews.plan_optimizer.test_crew [n_iterations]
"""

import json
import sys
from datetime import date
from pathlib import Path

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import asyncio

from dotenv import load_dotenv

load_dotenv()

from crewai_core.crews.academic_planner.crew import AcademicPlannerCrew
from crewai_core.crews.academic_planner.scheduling import allocate_days_to_subjects
from crewai_core.crews.plan_generator.crew import PlanGeneratorCrew
from crewai_core.crews.plan_optimizer.crew import PlanOptimizerCrew
from crewai_core.crews.syllabus_analyst.crew import SyllabusAnalystCrew
from crewai_core.flow import merge_subject_plans, split_remaining_days
from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.study_plan import StudyPlan
from crewai_core.models.syllabus import SyllabusStructure
from crewai_core.models.weak_topic import TopicStatus, WeakTopicUpdate

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


async def _analyze_subject(entry: dict) -> SyllabusStructure:
    crew_instance = SyllabusAnalystCrew(raw_syllabus=entry)
    output = await crew_instance.crew().kickoff_async(
        inputs={"raw_syllabus_json": crew_instance.raw_syllabus_text}
    )
    return output.pydantic


async def _generate_subject_plan(
    subject_syllabus: SyllabusStructure,
    day_budget: list[tuple[str, float]],
    calendar: CalendarStructure,
):
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
    return result.pydantic


async def _build_sample_inputs():
    """Runs the real Step 2-4 pipeline for all sample subjects, to get one
    real remaining-days StudyPlan slice to test the Plan Optimizer against.

    Both per-subject stages run CONCURRENTLY via asyncio.gather, same
    pattern as run_academic_planner.py / crewai_core/flow.py (deviation #5
    in docs/build/01-status-and-decisions.md) — this eval script previously
    ran them sequentially, which was the sole reason it took several times
    longer than the equivalent product-path pipeline for no benefit (same
    output either way; PlanGeneratorCrew calls are independent per subject,
    so there's no shared state to race on)."""
    with open(FIXTURES_DIR / "sample_syllabi.json", encoding="utf-8") as f:
        raw_syllabi = json.load(f)
    with open(FIXTURES_DIR / "sample_calendar.json", encoding="utf-8") as f:
        raw_calendar = json.load(f)

    all_syllabi = list(await asyncio.gather(*(_analyze_subject(e) for e in raw_syllabi)))

    planner_crew = AcademicPlannerCrew(raw_calendar=raw_calendar)
    calendar_result = await planner_crew.crew().kickoff_async(
        inputs={"raw_calendar_json": planner_crew.raw_calendar_text}
    )
    calendar: CalendarStructure = calendar_result.pydantic

    budget = allocate_days_to_subjects(calendar, all_syllabi)

    subject_plans = list(
        await asyncio.gather(
            *(
                _generate_subject_plan(s, budget[s.subject], calendar)
                for s in all_syllabi
            )
        )
    )

    study_plan: StudyPlan = merge_subject_plans(subject_plans)
    today = date.today().isoformat()
    _, remaining_days = split_remaining_days(study_plan, today)

    weak_topics = [
        WeakTopicUpdate(
            subject=all_syllabi[0].subject,
            topic_name=all_syllabi[0].units[0].topics[0].topic_name,
            status=TopicStatus.STRUGGLING,
            attempts_considered=3,
            accuracy=0.3,
        ),
    ]
    if len(all_syllabi) > 1 and all_syllabi[1].units[0].topics:
        weak_topics.append(
            WeakTopicUpdate(
                subject=all_syllabi[1].subject,
                topic_name=all_syllabi[1].units[0].topics[0].topic_name,
                status=TopicStatus.MASTERED,
                attempts_considered=5,
                accuracy=0.95,
            )
        )

    return remaining_days, all_syllabi, weak_topics, calendar.term_end


def main() -> None:
    n_iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 2

    remaining_days, all_syllabi, weak_topics, term_end = asyncio.run(_build_sample_inputs())

    crew_instance = PlanOptimizerCrew(
        remaining_days=remaining_days,
        all_syllabi=all_syllabi,
        weak_topics=weak_topics,
        term_end=term_end,
    )

    print(
        f"Testing PlanOptimizerCrew on {len(remaining_days)} remaining days, "
        f"{len(weak_topics)} weak-topic entries, for {n_iterations} iterations..."
    )
    crew_instance.crew().test(
        n_iterations=n_iterations,
        eval_llm="gpt-4o-mini",
        inputs={
            "remaining_plan_json": crew_instance.remaining_plan_text,
            "all_syllabi_json": crew_instance.all_syllabi_text,
            "weak_topics_json": crew_instance.weak_topics_text,
        },
    )


if __name__ == "__main__":
    main()
