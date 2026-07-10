"""Tests for backend/persistence_backend.py's Step 3 swappable-backend seam.

These are independent of backend/registry.py's facade and of any HTTP
layer — they exercise _select_backend() and InMemoryBackend directly.

backend/conftest.py sets CREWAI_STORAGE_DIR at module-import time so these
tests never touch the developer's real local CrewAI SQLite file.
"""

import pytest

from crewai.flow.persistence.sqlite import SQLiteFlowPersistence

from backend.persistence_backend import InMemoryBackend, _select_backend
from crewai_core.flow_id import derive_flow_id
from crewai_core.models.study_plan import DayPlan, StudyPlan, StudyPlanEntry


def test_select_backend_defaults_to_memory_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("REGISTRY_BACKEND", raising=False)
    backend = _select_backend()
    assert isinstance(backend, InMemoryBackend)


def test_select_backend_memory_explicit(monkeypatch):
    monkeypatch.setenv("REGISTRY_BACKEND", "memory")
    backend = _select_backend()
    assert isinstance(backend, InMemoryBackend)


def test_select_backend_postgres_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("REGISTRY_BACKEND", "postgres")
    with pytest.raises(NotImplementedError):
        _select_backend()


def test_select_backend_bogus_value_raises_value_error(monkeypatch):
    monkeypatch.setenv("REGISTRY_BACKEND", "totally-bogus-value")
    with pytest.raises(ValueError, match="totally-bogus-value"):
        _select_backend()


def test_in_memory_backend_satisfies_registry_backend_protocol():
    backend = InMemoryBackend()
    # Not a runtime_checkable Protocol, so this is a structural sanity check
    # rather than isinstance(backend, RegistryBackend) — confirm the
    # expected methods exist with the right names.
    assert hasattr(backend, "get")
    assert hasattr(backend, "create_or_replace")
    assert callable(backend.get)
    assert callable(backend.create_or_replace)


def test_in_memory_backend_standalone_create_and_get_round_trip():
    backend = InMemoryBackend()
    student_id = "standalone-student"
    raw_syllabi = [
        {
            "grade": "10",
            "subject": "TestSubject",
            "units": [
                {
                    "unit_name": "UnitA",
                    "weightage_percent": 100,
                    "topics": [{"topic_name": "TestTopic", "sub_topics": []}],
                }
            ],
        }
    ]
    raw_calendar = {
        "term_start": "2026-07-06",
        "term_end": "2026-07-10",
        "exam_dates": [],
        "assignment_deadlines": [],
        "weekly_available_hours": {
            "monday": 2, "tuesday": 2, "wednesday": 2, "thursday": 2,
            "friday": 2, "saturday": 2, "sunday": 2,
        },
        "recurring_activities": [],
        "personal_gaps": [],
    }

    flow, lock = backend.create_or_replace(student_id, raw_syllabi, raw_calendar)
    assert flow.state.student_id == student_id
    assert student_id in backend._registry

    fetched = backend.get(student_id)
    assert fetched is not None
    fetched_flow, fetched_lock = fetched
    assert fetched_flow is flow
    assert fetched_lock is lock


def test_in_memory_backend_standalone_rehydration_after_dict_miss():
    backend = InMemoryBackend()
    student_id = "standalone-rehydrate-student"
    flow_uuid = derive_flow_id(student_id)

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

    # No prior create_or_replace call on this fresh, standalone backend
    # instance — the dict starts empty, so get() must fall through to the
    # SQLite rehydration path exactly as backend/registry.py's facade does.
    result = backend.get(student_id)
    assert result is not None
    rehydrated_flow, rehydrated_lock = result
    assert rehydrated_flow.state.student_id == student_id
    assert rehydrated_flow.state.id == flow_uuid
    assert rehydrated_flow.state.study_plan is not None
    assert len(rehydrated_flow.state.study_plan.days) == 1
    assert rehydrated_flow.state.study_plan.days[0].entries[0].topic_name == "TestTopic"

    # Repopulates this backend instance's own dict, not any other instance's.
    assert backend._registry[student_id][0] is rehydrated_flow
    assert rehydrated_lock is not None


def test_in_memory_backend_standalone_unknown_student_returns_none():
    backend = InMemoryBackend()
    assert backend.get("student-who-never-existed-standalone") is None
