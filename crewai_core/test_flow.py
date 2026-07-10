"""Pytest coverage for StudyPlanFlow's construction-time state wiring
(Step 1 of the persistence-reliability plan): state.id must be the
deterministic derive_flow_id(student_id) value, and state.student_id must
actually be populated (previously a dead field, never written).

No LLM/Crew calls here — only Flow.__init__ runs, never kickoff_async().

Run with: uv run pytest crewai_core/test_flow.py
"""

from crewai_core.flow import StudyPlanFlow
from crewai_core.flow_id import derive_flow_id

SAMPLE_CALENDAR = {
    "term_start": "2026-01-01",
    "term_end": "2026-06-30",
}


def test_state_id_is_derived_from_student_id():
    flow = StudyPlanFlow(
        student_id="student-abc",
        raw_syllabi=[],
        raw_calendar=SAMPLE_CALENDAR,
    )

    assert flow.state.id == derive_flow_id("student-abc")


def test_state_student_id_is_populated():
    flow = StudyPlanFlow(
        student_id="student-abc",
        raw_syllabi=[],
        raw_calendar=SAMPLE_CALENDAR,
    )

    assert flow.state.student_id == "student-abc"


def test_two_different_students_get_two_different_flow_ids():
    flow_a = StudyPlanFlow(
        student_id="student-a",
        raw_syllabi=[],
        raw_calendar=SAMPLE_CALENDAR,
    )
    flow_b = StudyPlanFlow(
        student_id="student-b",
        raw_syllabi=[],
        raw_calendar=SAMPLE_CALENDAR,
    )

    assert flow_a.state.id != flow_b.state.id


def test_same_student_id_reconstructed_gets_same_flow_id():
    first = StudyPlanFlow(
        student_id="student-repeat",
        raw_syllabi=[],
        raw_calendar=SAMPLE_CALENDAR,
    )
    second = StudyPlanFlow(
        student_id="student-repeat",
        raw_syllabi=[],
        raw_calendar=SAMPLE_CALENDAR,
    )

    assert first.state.id == second.state.id
