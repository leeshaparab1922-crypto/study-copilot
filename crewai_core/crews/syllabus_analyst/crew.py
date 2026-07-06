import json

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from crewai_core.models.syllabus import SyllabusStructure

from .guardrails import make_syllabus_hallucination_guardrail


def log_step(step_output) -> None:
    print(f"[SyllabusAnalyst step] {step_output}")


@CrewBase
class SyllabusAnalystCrew:
    """Runs once per subject entry to extract a structured syllabus breakdown."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, raw_syllabus: dict):
        self.raw_syllabus = raw_syllabus
        self.raw_syllabus_text = json.dumps(raw_syllabus, ensure_ascii=False)

    @agent
    def syllabus_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["syllabus_analyst"],
            # Lowered from 10: run_syllabus_analyst.py / run_academic_planner.py
            # now run one SyllabusAnalystCrew per subject CONCURRENTLY (each
            # instance gets its own Agent/RPM controller), so aggregate request
            # rate scales with subject count. 5/agent x ~6 subjects ~= 30/min
            # aggregate, a bounded rate rather than an unbounded one.
            max_rpm=5,
            step_callback=log_step,
            verbose=True,
        )

    @task
    def analyze_syllabus_task(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_syllabus_task"],
            agent=self.syllabus_analyst(),
            output_pydantic=SyllabusStructure,
            guardrail=make_syllabus_hallucination_guardrail(self.raw_syllabus_text),
            guardrail_max_retries=3,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
