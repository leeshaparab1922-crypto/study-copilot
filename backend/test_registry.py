"""Tests for backend/registry.py's Step 2 rehydration path.

No LLM/Crew calls — these exercise registry.get()'s SQLite-fallback read
path directly against real CrewAI SQLite @persist() rows (written either
directly via SQLiteFlowPersistence, mirroring what crewai_core/flow.py's
@persist() decorator does automatically at the end of a real
@start()/@listen() method, or left absent/corrupt to test the miss paths).

backend/conftest.py sets CREWAI_STORAGE_DIR at module-import time (before
crewai_core.flow's @persist() decoration bakes in a fixed SQLite path — see
that file's comment for why), so these tests never touch the developer's
real local CrewAI SQLite file.
"""

from crewai.flow.persistence.sqlite import SQLiteFlowPersistence

from backend import registry
from crewai_core.flow_id import derive_flow_id
from crewai_core.models.study_plan import DayPlan, StudyPlan, StudyPlanEntry


def test_rehydration_round_trip_after_simulated_restart():
    student_id = "rehydrate-student"
    flow_uuid = derive_flow_id(student_id)

    # Write a real, valid StudyPlanFlowState row directly via
    # SQLiteFlowPersistence — this is exactly what crewai_core/flow.py's
    # @persist() decorator does automatically at the end of any
    # @start()/@listen()-graph method (e.g. generate_plan()); writing it
    # directly here keeps this test LLM/Crew-free while still exercising
    # the real read path registry.get() relies on (see
    # backend/test_routes.py's
    # test_get_plan_survives_registry_clear_simulating_restart for the
    # equivalent end-to-end HTTP-level regression test that goes through
    # the real @persist()-wrapped graph methods).
    study_plan = StudyPlan(
        days=[
            DayPlan(
                date="2026-07-10",
                entries=[
                    StudyPlanEntry(subject="TestSubject", topic_name="TestTopic", hours_allocated=2.0)
                ],
            )
        ]
    )
    persisted_state = {
        "id": flow_uuid,
        "student_id": student_id,
        "grade": "10",
        "syllabi": [],
        "calendar": None,
        "study_plan": study_plan.model_dump(),
        "quiz_history": [],
        "weak_topics": [],
        "wellbeing_flags": [],
    }
    SQLiteFlowPersistence().save_state(flow_uuid, "generate_plan", persisted_state)

    # Ensure there is no in-memory entry to begin with (simulates a process
    # restart: only the SQLite row on disk survives).
    registry._registry.pop(student_id, None)

    result = registry.get(student_id)
    assert result is not None
    rehydrated_flow, rehydrated_lock = result

    assert rehydrated_flow.state.student_id == student_id
    assert rehydrated_flow.state.id == flow_uuid
    assert rehydrated_flow.state.study_plan is not None
    assert len(rehydrated_flow.state.study_plan.days) == 1
    assert rehydrated_flow.state.study_plan.days[0].date == "2026-07-10"
    assert rehydrated_flow.state.study_plan.days[0].entries[0].topic_name == "TestTopic"

    # Rehydration also repopulates the in-memory dict so subsequent calls
    # hit the fast path.
    assert registry._registry[student_id][0] is rehydrated_flow
    assert rehydrated_lock is not None


def test_unknown_student_id_returns_none_no_false_positive_rehydration():
    assert registry.get("student-who-never-existed") is None


def test_corrupt_persisted_state_returns_none_not_an_exception():
    student_id = "corrupt-student"
    flow_uuid = derive_flow_id(student_id)

    # Write a garbage-shaped row directly, bypassing StudyPlanFlow/Flow
    # entirely, simulating schema drift or corruption. An unknown extra
    # field alone would NOT fail validation (pydantic's default is to
    # silently ignore unrecognized keys) — study_plan must be a real
    # StudyPlan shape or None, so a bogus dict there is what actually
    # trips StudyPlanFlowState.model_validate's ValidationError.
    SQLiteFlowPersistence().save_state(
        flow_uuid,
        "test",
        {"id": flow_uuid, "not_a_real_field": 123, "study_plan": {"bogus": True}},
    )

    result = registry.get(student_id)
    assert result is None
