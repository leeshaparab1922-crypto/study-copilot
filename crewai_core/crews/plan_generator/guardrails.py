"""Function-based guardrail for the (per-subject) Plan Generator task.

Checks, for ONE subject's day-wise plan slice, against that subject's
SyllabusStructure and its pre-computed day/hour budget
(from academic_planner/scheduling.py):
  1. Every topic in this subject's syllabus appears at least once in the plan.
  2. Every entry's topic_name is actually present in this subject's syllabus
     (no inventing topics, e.g. "Final Revision" / "Mock Test" that are not
     real syllabus topics).
  3. Every day used in the plan was actually assigned to this subject by the
     budget (no inventing extra days).
  4. No day's allocated hours exceed that day's budgeted hours for this
     subject.
  5. Every entry's status is exactly "not_started" — a freshly generated
     plan has no real-world student progress yet, so the LLM must not
     invent "in_progress"/"completed" values for a field it doesn't own
     (discovered live: without this check, the model would pick essentially
     random status values, which then confused the Plan Optimizer's
     status-preservation guardrail into "protecting" progress the student
     never actually made).
"""

from typing import Any

from crewai import TaskOutput

from crewai_core.models.study_plan import EntryStatus, StudyPlan
from crewai_core.models.syllabus import SyllabusStructure


def make_subject_plan_guardrail(
    subject_syllabus: SyllabusStructure, day_budget: list[tuple[str, float]]
):
    """Build a guardrail bound to one subject's syllabus and day/hour budget."""

    subject_name = subject_syllabus.subject
    all_topics = {topic.topic_name for unit in subject_syllabus.units for topic in unit.topics}
    budget_by_date = {day: hours for day, hours in day_budget}

    def guardrail(result: TaskOutput) -> tuple[bool, Any]:
        try:
            plan = StudyPlan.model_validate(
                result.pydantic if result.pydantic is not None else result.json_dict
            )
        except Exception as exc:
            return False, f"Output did not match StudyPlan schema: {exc}"

        problems: list[str] = []
        covered_topics: set[str] = set()

        for day_plan in plan.days:
            if day_plan.date not in budget_by_date:
                problems.append(
                    f"Day {day_plan.date} was not assigned to {subject_name} in the "
                    "day/hour budget — do not schedule days outside your assigned budget."
                )
                continue

            for entry in day_plan.entries:
                if entry.subject != subject_name:
                    problems.append(
                        f"Day {day_plan.date} contains an entry for subject "
                        f"'{entry.subject}', but this task is scoped to {subject_name} only."
                    )
                if entry.topic_name not in all_topics:
                    problems.append(
                        f"Day {day_plan.date} references topic '{entry.topic_name}', which "
                        f"is not present in {subject_name}'s syllabus — do not invent topics."
                    )
                if entry.status != EntryStatus.NOT_STARTED:
                    problems.append(
                        f"Day {day_plan.date} entry for topic '{entry.topic_name}' has status "
                        f"'{entry.status.value}', but a freshly generated plan must set every "
                        "entry's status to 'not_started' — this field tracks real student "
                        "progress, which does not exist yet."
                    )
                covered_topics.add(entry.topic_name)

            allocated_hours = sum(entry.hours_allocated for entry in day_plan.entries)
            budgeted_hours = budget_by_date[day_plan.date]
            if allocated_hours > budgeted_hours + 1e-9:
                problems.append(
                    f"Day {day_plan.date} allocates {allocated_hours}h but the budget for "
                    f"{subject_name} on that day is only {budgeted_hours}h."
                )

        missing_topics = all_topics - covered_topics
        if missing_topics:
            problems.append(
                f"The following {subject_name} topics never appear in the plan: "
                + ", ".join(sorted(missing_topics))
            )

        if problems:
            return False, "; ".join(problems)

        return True, plan

    return guardrail
