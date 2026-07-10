"""Swappable-backend seam for the student registry (Step 3).

Pure refactor: backend/registry.py's Step 1+2 logic (in-memory dict +
SQLite-fallback rehydration) is moved here VERBATIM as instance methods on
InMemoryBackend — no behavior change. backend/registry.py becomes a thin
facade that delegates to whichever backend `_select_backend()` picks (env
var REGISTRY_BACKEND, default "memory").

This exists so a future Phase B (e.g. a Postgres-backed registry) can be
added by implementing the same RegistryBackend Protocol without touching
backend/routes.py or any other call site — everything above the facade only
ever calls backend.registry.get/create_or_replace.
"""

import asyncio
import logging
import os
from typing import Protocol

from pydantic import ValidationError

from crewai.flow.persistence.sqlite import SQLiteFlowPersistence
from crewai_core.flow import StudyPlanFlow
from crewai_core.flow_id import derive_flow_id
from crewai_core.models.flow_state import StudyPlanFlowState
from crewai_core.models.syllabus import SyllabusStructure

logger = logging.getLogger(__name__)


class RegistryBackend(Protocol):
    """Matches backend/registry.py's (Step 2) finalized get/create_or_replace
    signatures exactly — any implementation is a drop-in for the facade."""

    def get(self, student_id: str) -> tuple[StudyPlanFlow, asyncio.Lock] | None: ...

    def create_or_replace(
        self,
        student_id: str,
        raw_syllabi: list[dict],
        raw_calendar: dict,
        pre_analyzed_syllabi: list[SyllabusStructure] | None = None,
    ) -> tuple[StudyPlanFlow, asyncio.Lock]: ...


class InMemoryBackend:
    """Steps 1+2's dict + rehydration logic, moved here verbatim as instance
    methods — self._registry is now instance state rather than a module-level
    global, but the logic/semantics are otherwise unchanged. See
    backend/registry.py's (pre-Step-3) history for the original docstrings
    this was extracted from.
    """

    def __init__(self) -> None:
        self._registry: dict[str, tuple[StudyPlanFlow, asyncio.Lock]] = {}

    def get(self, student_id: str) -> tuple[StudyPlanFlow, asyncio.Lock] | None:
        """Look up this student's (StudyPlanFlow, Lock).

        On a dict miss, attempts to rehydrate from CrewAI's own SQLite
        @persist() store (crewai_core/flow.py's StudyPlanFlow is decorated
        with @persist(), which already writes there automatically on every
        @start()/@listen()-graph step — no extra write path is needed here,
        only a read path). This is what makes a genuinely-existing student's
        plan survive a backend process restart, since the in-memory dict alone
        does not.

        Three outcomes:
          - In-memory HIT: return it directly, unchanged from before Step 2.
          - SQLite HIT (dict miss, but a persisted row exists for this
            student's derived flow_uuid and deserializes cleanly into
            StudyPlanFlowState): reconstruct a StudyPlanFlow around that
            state, wrap it in a FRESH asyncio.Lock (the old lock object, if
            any, died with the old process — there is nothing to preserve),
            insert into the in-memory dict so subsequent calls hit the fast
            path, and return it.
          - MISS/CORRUPT: genuinely-unknown student_id, or a persisted row
            exists but does not validate against the current
            StudyPlanFlowState shape (e.g. schema drift) — return None either
            way rather than raising. A 404 on stale/incompatible data beats
            crashing the request; a corrupt row is logged as a warning for
            operator visibility.
        """
        cached = self._registry.get(student_id)
        if cached is not None:
            return cached

        flow_uuid = derive_flow_id(student_id)
        loaded = SQLiteFlowPersistence().load_state(flow_uuid)
        if loaded is None:
            return None

        try:
            state = StudyPlanFlowState.model_validate(loaded)
        except ValidationError:
            logger.warning(
                "registry.get: found a persisted SQLite row for student_id=%r "
                "(flow_uuid=%r) but it did not validate against the current "
                "StudyPlanFlowState shape — treating as unknown/corrupt and "
                "returning None instead of raising.",
                student_id,
                flow_uuid,
            )
            return None

        flow = StudyPlanFlow(student_id=student_id, _initial_state=state)
        lock = asyncio.Lock()
        self._registry[student_id] = (flow, lock)
        print(
            f"=== registry: rehydrated Flow for student_id={student_id!r} from "
            "persisted SQLite state (in-memory registry entry was missing, "
            "e.g. after a process restart) ==="
        )
        return flow, lock

    def create_or_replace(
        self,
        student_id: str,
        raw_syllabi: list[dict],
        raw_calendar: dict,
        pre_analyzed_syllabi: list[SyllabusStructure] | None = None,
    ) -> tuple[StudyPlanFlow, asyncio.Lock]:
        """(Re)create the Flow for this student. A repeat call for a student_id
        that already has a Flow is a deliberate "start this student over": the
        prior Flow instance (and its accumulated quiz_history/weak_topics/
        wellbeing_flags) is discarded, not merged or rejected.

        pre_analyzed_syllabi: passed straight through to StudyPlanFlow — see
        its docstring. backend/routes.py's /plan already converts each
        subject's raw text via SyllabusExtractorCrew before calling this, so
        the Flow must not re-run SyllabusAnalystCrew on already-clean data.
        """
        if student_id in self._registry:
            print(
                f"=== registry: replacing existing Flow for student_id={student_id!r} — "
                "prior quiz_history/weak_topics/wellbeing_flags are discarded ==="
            )

        flow = StudyPlanFlow(
            student_id=student_id,
            raw_syllabi=raw_syllabi,
            raw_calendar=raw_calendar,
            pre_analyzed_syllabi=pre_analyzed_syllabi,
        )
        lock = asyncio.Lock()
        self._registry[student_id] = (flow, lock)
        return flow, lock


def _select_backend() -> RegistryBackend:
    """Reads REGISTRY_BACKEND (default "memory") to pick a backend
    implementation. Called once, at backend/registry.py's module import
    time — not re-read per-request.
    """
    backend_name = os.environ.get("REGISTRY_BACKEND", "memory")
    if backend_name == "memory":
        return InMemoryBackend()
    if backend_name == "postgres":
        raise NotImplementedError(
            "REGISTRY_BACKEND=postgres is not implemented yet — Phase B "
            "(a Postgres-backed registry) has not been built. Use "
            "REGISTRY_BACKEND=memory (or leave it unset) for now."
        )
    raise ValueError(
        f"Unknown REGISTRY_BACKEND value: {backend_name!r}. "
        "Valid values are 'memory' (default) or 'postgres' (not yet implemented)."
    )
