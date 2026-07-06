from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from crewai_core.models.quiz import QuizSet
from crewai_core.models.syllabus import SyllabusStructure

from .guardrails import make_assessment_guardrail


def log_step(step_output) -> None:
    print(f"[AssessmentDesigner step] {step_output}")


@CrewBase
class AssessmentDesignerCrew:
    """Produces one on-demand quiz for one (subject, topic) pair, requested
    directly by the student — not tied to any day in the study plan. The
    requested topic only needs to exist in that subject's syllabus, not in
    any particular day's plan entries."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, subject_name: str, topic_name: str, syllabus: SyllabusStructure):
        self.subject_name = subject_name
        self.topic_name = topic_name
        self.syllabus = syllabus

    @agent
    def assessment_designer(self) -> Agent:
        return Agent(
            config=self.agents_config["assessment_designer"],
            max_rpm=5,
            step_callback=log_step,
            verbose=True,
        )

    @task
    def generate_quiz_task(self) -> Task:
        return Task(
            config=self.tasks_config["generate_quiz_task"],
            agent=self.assessment_designer(),
            output_pydantic=QuizSet,
            guardrail=make_assessment_guardrail(self.subject_name, self.topic_name, self.syllabus),
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
