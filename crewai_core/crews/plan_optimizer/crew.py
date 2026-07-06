import json

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from crewai_core.models.plan_revision import PlanRevision
from crewai_core.models.study_plan import DayPlan
from crewai_core.models.syllabus import SyllabusStructure
from crewai_core.models.weak_topic import WeakTopicUpdate

from .guardrails import make_plan_optimizer_guardrail


def log_step(step_output) -> None:
    print(f"[PlanOptimizer step] {step_output}")


@CrewBase
class PlanOptimizerCrew:
    """Step 7 (Section 2.2 #4): revises only the remaining (>= today) days
    of the student's study plan, across ALL subjects at once (unlike
    SyllabusAnalystCrew/PlanGeneratorCrew/AssessmentDesignerCrew, which are
    invoked once per subject) — the whole point of this Crew is reasoning
    about weak topics ACROSS subjects to reprioritize, so a single call
    needs the full cross-subject picture, not a per-subject slice.

    This is the ONE Crew in the project allowed memory=True (Section 3.4's
    narrow, explicit exception) — continuity across repeated re-planning
    calls for the same student is useful here specifically."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(
        self,
        remaining_days: list[DayPlan],
        all_syllabi: list[SyllabusStructure],
        weak_topics: list[WeakTopicUpdate],
        term_end: str,
    ):
        self.remaining_days = remaining_days
        self.all_syllabi = all_syllabi
        self.weak_topics = weak_topics
        self.term_end = term_end

        self.remaining_day_budgets = {
            day.date: sum(entry.hours_allocated for entry in day.entries) for day in remaining_days
        }
        self.remaining_plan_text = json.dumps(
            [day.model_dump() for day in remaining_days], ensure_ascii=False
        )
        self.all_syllabi_text = json.dumps(
            [s.model_dump() for s in all_syllabi], ensure_ascii=False
        )
        self.weak_topics_text = json.dumps(
            [wt.model_dump(mode="json") for wt in weak_topics], ensure_ascii=False
        )

    @agent
    def plan_optimizer(self) -> Agent:
        return Agent(
            config=self.agents_config["plan_optimizer"],
            max_rpm=5,
            step_callback=log_step,
            verbose=True,
        )

    @task
    def optimize_plan_task(self) -> Task:
        return Task(
            config=self.tasks_config["optimize_plan_task"],
            agent=self.plan_optimizer(),
            output_pydantic=PlanRevision,
            guardrail=make_plan_optimizer_guardrail(
                self.remaining_day_budgets, self.term_end, self.all_syllabi, self.weak_topics
            ),
            guardrail_max_retries=3,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            memory=True,  # Section 3.4's narrow, explicit exception — this Crew only.
            verbose=True,
        )
