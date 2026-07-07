"""Pytest coverage for make_plan_optimizer_guardrail's decision logic — no
real LLM calls, same style as crews/syllabus_extractor/test_guardrails.py.

Original 6 cases (per docs/build/03-verification-records.md's Step 7
record, previously verified via a throwaway script, now checked in as real
pytest coverage): valid revision passes; invented date fails; over-budget
hours fails; dropping a non-Mastered topic fails; invented topic fails;
scheduling past term_end fails.

2 new cases (Task 3, added when StudyPlanEntry.status was introduced):
preserving a completed/in_progress entry's status passes; silently
resetting one to not_started on an otherwise-unchanged entry fails.

Run with: uv run pytest crewai_core/crews/plan_optimizer/test_guardrails.py
"""

from types import SimpleNamespace

from crewai_core.crews.plan_optimizer.guardrails import make_plan_optimizer_guardrail
from crewai_core.models.plan_revision import PlanRevision
from crewai_core.models.study_plan import DayPlan, EntryStatus, StudyPlanEntry
from crewai_core.models.syllabus import SyllabusStructure, SyllabusTopic, SyllabusUnit
from crewai_core.models.weak_topic import TopicStatus, WeakTopicUpdate

SUBJECT = "Mathematics"
TOPIC_STRUGGLING = "Polynomials"
TOPIC_MASTERED = "Trigonometry"
TERM_END = "2026-08-31"

SYLLABI = [
    SyllabusStructure(
        grade="10",
        subject=SUBJECT,
        units=[
            SyllabusUnit(
                unit_name="Algebra",
                weightage_percent=100,
                topics=[
                    SyllabusTopic(topic_name=TOPIC_STRUGGLING, sub_topics=[]),
                    SyllabusTopic(topic_name=TOPIC_MASTERED, sub_topics=[]),
                ],
            )
        ],
    )
]

WEAK_TOPICS = [
    WeakTopicUpdate(
        subject=SUBJECT, topic_name=TOPIC_STRUGGLING, status=TopicStatus.STRUGGLING,
        attempts_considered=3, accuracy=0.3,
    ),
    WeakTopicUpdate(
        subject=SUBJECT, topic_name=TOPIC_MASTERED, status=TopicStatus.MASTERED,
        attempts_considered=5, accuracy=0.95,
    ),
]

REMAINING_DAY_BUDGETS = {"2026-07-10": 2.0, "2026-07-11": 2.0}

ORIGINAL_REMAINING_DAYS = [
    DayPlan(
        date="2026-07-10",
        entries=[
            StudyPlanEntry(
                subject=SUBJECT, topic_name=TOPIC_STRUGGLING, hours_allocated=2.0,
                status=EntryStatus.NOT_STARTED,
            )
        ],
    ),
    DayPlan(
        date="2026-07-11",
        entries=[
            StudyPlanEntry(
                subject=SUBJECT, topic_name=TOPIC_MASTERED, hours_allocated=2.0,
                status=EntryStatus.COMPLETED,
            )
        ],
    ),
]


def _make_guardrail(original_remaining_days=ORIGINAL_REMAINING_DAYS):
    return make_plan_optimizer_guardrail(
        REMAINING_DAY_BUDGETS, TERM_END, SYLLABI, WEAK_TOPICS,
        original_remaining_days=original_remaining_days,
    )


def _result_for(revision: PlanRevision):
    return SimpleNamespace(pydantic=revision, json_dict=None)


def test_valid_revision_passes():
    guardrail = _make_guardrail()
    revision = PlanRevision(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_STRUGGLING, hours_allocated=2.0),
            ]),
        ]
    )
    ok, _ = guardrail(_result_for(revision))
    assert ok is True


def test_invented_date_fails():
    guardrail = _make_guardrail()
    revision = PlanRevision(
        days=[
            DayPlan(date="2099-01-01", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_STRUGGLING, hours_allocated=2.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(revision))
    assert ok is False
    assert "not one of the original remaining days" in reason


def test_over_budget_hours_fails():
    guardrail = _make_guardrail()
    revision = PlanRevision(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_STRUGGLING, hours_allocated=99.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(revision))
    assert ok is False
    assert "budget was only" in reason


def test_dropping_non_mastered_topic_fails():
    guardrail = _make_guardrail()
    # Omits TOPIC_STRUGGLING entirely — Struggling topics must still appear.
    revision = PlanRevision(days=[DayPlan(date="2026-07-10", entries=[])])
    ok, reason = guardrail(_result_for(revision))
    assert ok is False
    assert "not yet Mastered" in reason


def test_invented_topic_fails():
    guardrail = _make_guardrail()
    revision = PlanRevision(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name="Not A Real Topic", hours_allocated=2.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(revision))
    assert ok is False
    assert "not present in" in reason


def test_scheduling_past_term_end_fails():
    guardrail = make_plan_optimizer_guardrail(
        {"2026-09-01": 2.0}, TERM_END, SYLLABI, WEAK_TOPICS,
        original_remaining_days=None,
    )
    revision = PlanRevision(
        days=[
            DayPlan(date="2026-09-01", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_STRUGGLING, hours_allocated=2.0),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(revision))
    assert ok is False
    assert "past term_end" in reason


def test_preserving_completed_status_passes():
    guardrail = _make_guardrail()
    # Same (date, subject, topic) as the original COMPLETED entry, status
    # correctly copied forward.
    revision = PlanRevision(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_STRUGGLING, hours_allocated=2.0),
            ]),
            DayPlan(date="2026-07-11", entries=[
                StudyPlanEntry(
                    subject=SUBJECT, topic_name=TOPIC_MASTERED, hours_allocated=2.0,
                    status=EntryStatus.COMPLETED,
                ),
            ]),
        ]
    )
    ok, _ = guardrail(_result_for(revision))
    assert ok is True


def test_silently_resetting_completed_status_fails():
    guardrail = _make_guardrail()
    # Same (date, subject, topic) as the original COMPLETED entry, but the
    # revision resets it to not_started — must be rejected.
    revision = PlanRevision(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_STRUGGLING, hours_allocated=2.0),
            ]),
            DayPlan(date="2026-07-11", entries=[
                StudyPlanEntry(
                    subject=SUBJECT, topic_name=TOPIC_MASTERED, hours_allocated=2.0,
                    status=EntryStatus.NOT_STARTED,
                ),
            ]),
        ]
    )
    ok, reason = guardrail(_result_for(revision))
    assert ok is False
    assert "was 'completed'" in reason
    assert "preserve the student's already-recorded progress" in reason


def test_original_remaining_days_none_skips_status_check():
    # Backward compatibility: without original_remaining_days, status
    # preservation is simply not checked (no crash, no false rejection).
    guardrail = _make_guardrail(original_remaining_days=None)
    revision = PlanRevision(
        days=[
            DayPlan(date="2026-07-10", entries=[
                StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC_STRUGGLING, hours_allocated=2.0),
            ]),
            DayPlan(date="2026-07-11", entries=[
                StudyPlanEntry(
                    subject=SUBJECT, topic_name=TOPIC_MASTERED, hours_allocated=2.0,
                    status=EntryStatus.NOT_STARTED,
                ),
            ]),
        ]
    )
    ok, _ = guardrail(_result_for(revision))
    assert ok is True
