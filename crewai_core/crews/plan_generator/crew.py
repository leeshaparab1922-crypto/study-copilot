import json

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.study_plan import StudyPlan
from crewai_core.models.syllabus import SyllabusStructure

from .guardrails import make_subject_plan_guardrail


def log_step(step_output) -> None:
    print(f"[PlanGenerator step] {step_output}")


@CrewBase
class PlanGeneratorCrew:
    """Produces one subject's day-wise study plan slice, given that subject's
    topic list and a pre-computed (date, available_hours) budget for that
    subject only (see academic_planner/scheduling.py). Invoked once per
    subject; results are merged in plain Python by the caller."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(
        self,
        subject_syllabus: SyllabusStructure,
        day_budget: list[tuple[str, float]],
        calendar: CalendarStructure,
    ):
        self.subject_syllabus = subject_syllabus
        self.day_budget = day_budget
        self.calendar = calendar

        self.subject_name = subject_syllabus.subject
        self.subject_syllabus_text = json.dumps(subject_syllabus.model_dump(), ensure_ascii=False)
        self.day_budget_text = json.dumps(
            [{"date": d, "available_hours": h} for d, h in day_budget], ensure_ascii=False
        )
        self.exams_and_deadlines_text = json.dumps(
            {
                "exam_dates": [e.model_dump() for e in calendar.exam_dates],
                "assignment_deadlines": [d.model_dump() for d in calendar.assignment_deadlines],
            },
            ensure_ascii=False,
        )

    @agent
    def plan_generator(self) -> Agent:
        return Agent(
            config=self.agents_config["plan_generator"],
            # Lowered from 10: run_academic_planner.py now runs one
            # PlanGeneratorCrew per subject CONCURRENTLY (each instance gets
            # its own Agent/RPM controller), so aggregate request rate scales
            # with subject count. 5/agent x ~6 subjects ~= 30/min aggregate,
            # a bounded rate rather than an unbounded one.
            max_rpm=5,
            step_callback=log_step,
            verbose=True,
        )

    @task
    def generate_subject_plan_task(self) -> Task:
        return Task(
            config=self.tasks_config["generate_subject_plan_task"],
            agent=self.plan_generator(),
            output_pydantic=StudyPlan,
            guardrail=make_subject_plan_guardrail(self.subject_syllabus, self.day_budget),
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
