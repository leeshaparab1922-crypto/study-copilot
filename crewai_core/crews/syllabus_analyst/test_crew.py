"""Evaluate the Syllabus Analyst Crew via CrewAI's built-in test/eval harness
(Crew.test), per Section 3.6 of the build prompt. Equivalent to `crewai test`
but invoked directly since this project holds multiple independent crews
rather than the single-crew-per-project shape the `crewai test` CLI assumes.

Usage:
    uv run python -m crewai_core.crews.syllabus_analyst.test_crew [n_iterations]
"""

import json
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from crewai_core.crews.syllabus_analyst.crew import SyllabusAnalystCrew

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def main() -> None:
    n_iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 2

    with open(FIXTURES_DIR / "sample_syllabi.json", encoding="utf-8") as f:
        syllabi = json.load(f)

    subject_entry = syllabi[0]  # Mathematics
    crew_instance = SyllabusAnalystCrew(raw_syllabus=subject_entry)

    print(f"Testing SyllabusAnalystCrew on '{subject_entry['subject']}' for {n_iterations} iterations...")
    crew_instance.crew().test(
        n_iterations=n_iterations,
        eval_llm="gpt-4o-mini",
        inputs={"raw_syllabus_json": crew_instance.raw_syllabus_text},
    )


if __name__ == "__main__":
    main()
