"""Facade over the swappable registry backend (backend/persistence_backend.py).

Primarily in-memory, per student, for the lifetime of this process — but
get() (Step 2) falls back to rehydrating from CrewAI's own @persist()
SQLite store on a dict miss, so a process restart no longer means a
genuinely-existing student's plan/state is unreachable. This is a read-path
recovery only: the in-memory dict is still authoritative and is not itself
persisted/loaded eagerly at startup, and create_or_replace()'s "start over"
semantics (discarding prior in-memory quiz_history/weak_topics/
wellbeing_flags on replace) are unchanged.

Step 3: the actual in-memory-dict + rehydration logic now lives in
backend/persistence_backend.py's InMemoryBackend, selected once at import
time via _select_backend() (env var REGISTRY_BACKEND, default "memory").
This module is a thin facade so every existing call site
(backend/routes.py, tests) keeps working unmodified — get/create_or_replace
just delegate to _backend.

`_registry` is kept as a module-level alias (not a copy) of the backend's
real dict, since backend/test_routes.py's autouse fixture does
`registry._registry.clear()` and relies on mutating the SAME dict object
the backend uses internally.

Every operation that touches flow.state must hold that student's lock for
its full duration (see backend/routes.py) — this registry only owns
construction/replacement of the (Flow, Lock) pair, not the locking
discipline around using them.
"""

import asyncio

from backend.persistence_backend import _select_backend
from crewai_core.flow import StudyPlanFlow
from crewai_core.models.syllabus import SyllabusStructure

_backend = _select_backend()

# Alias to the backend's real dict (not a copy) — preserves existing tests'
# direct mutation of registry._registry.
_registry = _backend._registry


def get(student_id: str) -> tuple[StudyPlanFlow, asyncio.Lock] | None:
    """Look up this student's (StudyPlanFlow, Lock). See
    backend/persistence_backend.py's InMemoryBackend.get for full semantics
    (in-memory hit / SQLite-rehydration hit / miss-or-corrupt -> None).
    """
    return _backend.get(student_id)


def create_or_replace(
    student_id: str,
    raw_syllabi: list[dict],
    raw_calendar: dict,
    pre_analyzed_syllabi: list[SyllabusStructure] | None = None,
) -> tuple[StudyPlanFlow, asyncio.Lock]:
    """(Re)create the Flow for this student — a deliberate "start over". See
    backend/persistence_backend.py's InMemoryBackend.create_or_replace for
    full semantics.
    """
    return _backend.create_or_replace(
        student_id, raw_syllabi, raw_calendar, pre_analyzed_syllabi
    )
