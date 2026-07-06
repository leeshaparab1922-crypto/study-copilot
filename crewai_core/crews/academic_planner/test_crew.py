"""Evaluate the Academic Planner Crew (calendar parsing only) via CrewAI's
built-in test/eval harness (Crew.test), per Section 3.6 of the build prompt.

Usage:
    uv run python -m crewai_core.crews.academic_planner.test_crew [n_iterations]
"""

import json
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from crewai_core.crews.academic_planner.crew import AcademicPlannerCrew

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def main() -> None:
    n_iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 2

    with open(FIXTURES_DIR / "sample_calendar.json", encoding="utf-8") as f:
        raw_calendar = json.load(f)

    crew_instance = AcademicPlannerCrew(raw_calendar=raw_calendar)

    print(f"Testing AcademicPlannerCrew for {n_iterations} iterations...")
    crew_instance.crew().test(
        n_iterations=n_iterations,
        eval_llm="gpt-4o-mini",
        inputs={"raw_calendar_json": crew_instance.raw_calendar_text},
    )


if __name__ == "__main__":
    main()
