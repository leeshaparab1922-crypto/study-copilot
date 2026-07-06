"""Manual runner: executes the Syllabus Analyst Crew once per subject entry
in the sample fixture, CONCURRENTLY (one independent Crew/Agent instance per
subject, run via asyncio.gather + Crew.kickoff_async), and prints each
resulting SyllabusStructure.

Usage:
    uv run python -m crewai_core.run_syllabus_analyst
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

from crewai_core.crews.syllabus_analyst.crew import SyllabusAnalystCrew
from crewai_core.models.syllabus import SyllabusStructure

FIXTURES_DIR = Path(__file__).parent / "fixtures"


async def analyze_subject(subject_entry: dict) -> SyllabusStructure:
    print(f"=== Starting {subject_entry['subject']} ===")
    crew_instance = SyllabusAnalystCrew(raw_syllabus=subject_entry)
    output = await crew_instance.crew().kickoff_async(
        inputs={"raw_syllabus_json": crew_instance.raw_syllabus_text}
    )
    print(f"=== Finished {subject_entry['subject']} ===")
    return output.pydantic


async def analyze_all_subjects(syllabi: list[dict]) -> list[SyllabusStructure]:
    return await asyncio.gather(*(analyze_subject(entry) for entry in syllabi))


def main() -> None:
    with open(FIXTURES_DIR / "sample_syllabi.json", encoding="utf-8") as f:
        syllabi = json.load(f)

    results = asyncio.run(analyze_all_subjects(syllabi))

    for structure in results:
        print(f"\n=== {structure.subject} ===")
        print(structure.model_dump_json(indent=2))

    print(f"\nDone. {len(results)} subjects processed (concurrently).")


if __name__ == "__main__":
    main()
