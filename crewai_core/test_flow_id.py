"""Pytest coverage for crewai_core/flow_id.py's deterministic derivation —
no LLM call, pure function, same style as crewai_core/test_entry_status.py.

Run with: uv run pytest crewai_core/test_flow_id.py
"""

import uuid

from crewai_core.flow_id import derive_flow_id


def test_same_student_id_produces_same_derived_id_across_calls():
    student_id = "student-42"
    first = derive_flow_id(student_id)
    second = derive_flow_id(student_id)
    third = derive_flow_id(student_id)

    assert first == second == third


def test_different_student_ids_produce_different_derived_ids():
    student_ids = [f"student-{i}" for i in range(100)]
    derived_ids = [derive_flow_id(sid) for sid in student_ids]

    assert len(set(derived_ids)) == len(student_ids)


def test_derived_id_parses_as_a_valid_uuid():
    derived = derive_flow_id("some-student")

    # Raises ValueError if not a valid UUID string — asserting no raise.
    parsed = uuid.UUID(derived)
    assert str(parsed) == derived
