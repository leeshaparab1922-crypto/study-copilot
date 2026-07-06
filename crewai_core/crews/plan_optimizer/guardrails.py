"""Function-based guardrail for the Plan Optimizer task (Step 7, Section
2.2 #4 + Section 3.1).

Checks the revised PlanRevision (covering only the remaining days, i.e.
days >= today, of the term) against:
  1. Every day used in the revision was actually one of the ORIGINAL
     remaining days (no inventing new dates, no scheduling before today).
  2. No day is scheduled past term_end.
  3. No day's allocated hours exceed that day's ORIGINAL budgeted hours
     (the hours a day had in the pre-revision plan) — the optimizer may
     redistribute WHICH topics land on a day, not invent extra study time.
  4. Every subject/topic that is not currently Mastered (per
     state.weak_topics) must still appear at least once somewhere in the
     revised remaining-days plan — Section 2.2 #4's "must not drop any
     subject/topic that hadn't already been marked Mastered." A topic with
     no weak_topics entry yet (never attempted) counts as not-Mastered and
     must still appear.
  5. Every entry's topic_name must actually exist in that subject's real
     syllabus (no invented topics — same class of check as the original
     Plan Generator guardrail, deviation #4's second bullet in
     01-status-and-decisions.md).
"""

from typing import Any

from crewai import TaskOutput

from crewai_core.models.plan_revision import PlanRevision
from crewai_core.models.syllabus import SyllabusStructure
from crewai_core.models.weak_topic import TopicStatus, WeakTopicUpdate


def make_plan_optimizer_guardrail(
    remaining_day_budgets: dict[str, float],
    term_end: str,
    all_syllabi: list[SyllabusStructure],
    weak_topics: list[WeakTopicUpdate],
):
    """Build a guardrail bound to the remaining-days budget, term_end, all
    subjects' syllabi, and the current weak-topic rollup state."""

    valid_topics_by_subject: dict[str, set[str]] = {
        syllabus.subject: {topic.topic_name for unit in syllabus.units for topic in unit.topics}
        for syllabus in all_syllabi
    }
    all_topic_pairs = {
        (subject, topic) for subject, topics in valid_topics_by_subject.items() for topic in topics
    }
    mastered_pairs = {
        (wt.subject, wt.topic_name) for wt in weak_topics if wt.status == TopicStatus.MASTERED
    }
    must_still_appear = all_topic_pairs - mastered_pairs

    def guardrail(result: TaskOutput) -> tuple[bool, Any]:
        try:
            revision = PlanRevision.model_validate(
                result.pydantic if result.pydantic is not None else result.json_dict
            )
        except Exception as exc:
            return False, f"Output did not match PlanRevision schema: {exc}"

        problems: list[str] = []
        covered_pairs: set[tuple[str, str]] = set()

        for day_plan in revision.days:
            if day_plan.date not in remaining_day_budgets:
                problems.append(
                    f"Day {day_plan.date} is not one of the original remaining days — "
                    "do not invent new dates or schedule before today."
                )
                continue
            if day_plan.date > term_end:
                problems.append(f"Day {day_plan.date} is scheduled past term_end ({term_end}).")

            allocated_hours = sum(entry.hours_allocated for entry in day_plan.entries)
            budgeted_hours = remaining_day_budgets[day_plan.date]
            if allocated_hours > budgeted_hours + 1e-9:
                problems.append(
                    f"Day {day_plan.date} allocates {allocated_hours}h but its original "
                    f"budget was only {budgeted_hours}h."
                )

            for entry in day_plan.entries:
                valid_topics = valid_topics_by_subject.get(entry.subject)
                if valid_topics is None:
                    problems.append(
                        f"Day {day_plan.date} references unknown subject '{entry.subject}'."
                    )
                    continue
                if entry.topic_name not in valid_topics:
                    problems.append(
                        f"Day {day_plan.date} references topic '{entry.topic_name}', which is "
                        f"not present in {entry.subject}'s syllabus — do not invent topics."
                    )
                covered_pairs.add((entry.subject, entry.topic_name))

        missing_pairs = must_still_appear - covered_pairs
        if missing_pairs:
            problems.append(
                "The following (subject, topic) pairs are not yet Mastered but do not "
                "appear anywhere in the revised remaining-days plan: "
                + ", ".join(f"{s}/{t}" for s, t in sorted(missing_pairs))
            )

        if problems:
            return False, "; ".join(problems)

        return True, revision

    return guardrail
