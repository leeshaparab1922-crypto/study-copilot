import json

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from crewai_core.models.calendar import CalendarStructure


def log_step(step_output) -> None:
    print(f"[AcademicPlanner step] {step_output}")


@CrewBase
class AcademicPlannerCrew:
    """Parses the raw academic calendar JSON into a structured CalendarStructure.

    Runs once per student. The resulting CalendarStructure feeds both the
    plain-Python day/hour budget allocator (scheduling.py) and the
    PlanGeneratorCrew (invoked once per subject) — see run_academic_planner.py.
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, raw_calendar: dict):
        self.raw_calendar = raw_calendar
        self.raw_calendar_text = json.dumps(raw_calendar, ensure_ascii=False)

    @agent
    def academic_planner(self) -> Agent:
        return Agent(
            config=self.agents_config["academic_planner"],
            max_rpm=10,
            step_callback=log_step,
            verbose=True,
        )

    @task
    def parse_calendar_task(self) -> Task:
        return Task(
            config=self.tasks_config["parse_calendar_task"],
            agent=self.academic_planner(),
            output_pydantic=CalendarStructure,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
