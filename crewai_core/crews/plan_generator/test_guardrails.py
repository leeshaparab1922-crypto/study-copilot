"""Pytest coverage for make_subject_plan_guardrail's decision logic — no
real LLM calls, same style as crews/syllabus_extractor/test_guardrails.py
and crews/plan_optimizer/test_guardrails.py.

5 cases: valid plan passes; day outside the assigned budget fails;
over-budget hours on a day fails; a plan missing a real syllabus topic
fails; an invented (non-syllabus) topic fails. Plus 1 new case (added when
StudyPlanEntry.status was introduced): a freshly generated entry with a
non-"not_started" status fails — this is the exact live bug found by
running crews/plan_optimizer/test_crew.py after Task 3's prompt/guardrail
changes (the LLM was inventing "in_progress"/"completed" values for a
field it was never told the meaning of, since PlanGeneratorCrew's prompt
predates the status field).

Run with: uv run pytest crewai_core/crews/plan_generator/test_guardrails.py
"""

from types import SimpleNamespace

from crewai_core.crews.plan_generator.guardrails import make_subject_plan_guardrail
from crewai_core.models.study_plan import DayPlan, EntryStatus, StudyPlan, StudyPlanEntry
from crewai_core.models.syllabus import SyllabusStructure, SyllabusTopic, SyllabusUnit

SUBJECT = "Mathematics"
TOPIC_A = "Polynomials"
TOPIC_B = "Trigonometry"

SYLLABUS = SyllabusStructure(
    grade="10",
    subject=SUBJECT,
    units=[
        SyllabusUnit(
            unit_name="Algebra",
            weightage_percent=100,
            topics=[
                SyllabusTopic(topic_name=TOPIC_A, sub_topics=[]),
                SyllabusTopic(topic_name=TOPIC_B, sub_topics=[]),
            ],
        )
    ],
)

DAY_BUDGET = [("2026-07-10", 2.0), ("2026-07-11", 2.0)]


def _make_guardrail():
    return make_subject_plan_guardrail(SYLLABUS, DAY_BUDGET)


def _result_for(plan: StudyPlan):
    return SimpleNamespace(pydantic=plan, json_dict=None)


def test_valid_plan_passes():
    guardrail = _make_guardrail()
    plan = StudyPlan(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_A, hours_allocated=2.0),
            ]),
            DayPlan(date="2026-07-11", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_B, hours_allocated=2.0),
            ]),
        ]
    )
    ok, _ = guardrail(_result_for(plan))
    assert ok is True


def test_day_outside_budget_fails():
    guardrail = _make_guardrail()
    plan = StudyPlan(
        days=[
            DayPlan(date="2099-01-01", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_A, hours_allocated=2.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(plan))
    assert ok is False
    assert "not assigned to" in reason


def test_over_budget_hours_fails():
    guardrail = _make_guardrail()
    plan = StudyPlan(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_A, hours_allocated=99.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(plan))
    assert ok is False
    assert "budget for" in reason


def test_missing_topic_fails():
    guardrail = _make_guardrail()
    # TOPIC_B never appears anywhere in the plan.
    plan = StudyPlan(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_A, hours_allocated=2.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(plan))
    assert ok is False
    assert "never appear" in reason


def test_invented_topic_fails():
    guardrail = _make_guardrail()
    plan = StudyPlan(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name="Not A Real Topic", hours_allocated=2.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(plan))
    assert ok is False
    assert "not present in" in reason


def test_non_not_started_status_on_generation_fails():
    guardrail = _make_guardrail()
    plan = StudyPlan(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(
                    subject=SUBJECT, topic_name=TOPIC_A, hours_allocated=2.0,
                    status=EntryStatus.IN_PROGRESS,
                ),
            ]),
            DayPlan(date="2026-07-11", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_B, hours_allocated=2.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(plan))
    assert ok is False
    assert "must set every entry's status to 'not_started'" in reason
