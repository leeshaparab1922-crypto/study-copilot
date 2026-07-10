"""Deterministic Flow id derivation from a student_id.

Pure, deterministic, no I/O, no randomness: the same student_id always
produces the same derived id (a valid UUID string), and different
student_ids produce different derived ids. This is what lets
backend/registry.py reuse the SAME underlying CrewAI SQLite flow_uuid
across a "start over" replace (Step 1's confirmed design decision #1) and
lets a rehydration path (Step 2) recompute the right key to look up without
storing any extra mapping.
"""

import uuid

# Fixed, arbitrary namespace UUID for this application's student_id -> flow
# id derivation. Never change this constant — changing it would silently
# orphan every previously-persisted Flow state (a new namespace produces a
# completely different derived id for the same student_id).
NAMESPACE = uuid.UUID("2f6a6e2e-2f8b-4c9e-9a2b-2f8b7a6e2e2f")


def derive_flow_id(student_id: str) -> str:
    """Deterministically derive a Flow state id from a student_id.

    Same student_id -> same derived id, always. Uses uuid5 (SHA-1 based,
    deterministic) rather than uuid4 (random) precisely so this can be
    recomputed later purely from student_id, with no lookup table needed.
    """
    return str(uuid.uuid5(NAMESPACE, student_id))
