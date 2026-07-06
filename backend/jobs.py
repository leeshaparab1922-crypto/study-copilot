"""Minimal in-memory background job store.

A job wraps one coroutine (e.g. a Flow operation run under a student's
lock) as an asyncio.Task, so the HTTP route that started it can return
immediately (202) and the caller polls GET /jobs/{job_id} for the result.
In-memory only — jobs vanish on process restart, same as the registry.
"""

import asyncio
from typing import Any, Coroutine
from uuid import uuid4

from backend.errors import classify_job_exception

_jobs: dict[str, dict[str, Any]] = {}


def get(job_id: str) -> dict[str, Any] | None:
    return _jobs.get(job_id)


def run_job(coro: Coroutine[Any, Any, Any]) -> str:
    """Schedule coro as a background asyncio.Task under a fresh job id.

    On failure, the stored record's http_status is set by classifying the
    exception (backend.errors.classify_job_exception) — the specific
    422/502/409 mapping is only knowable once the coroutine actually raises,
    which happens after the route that called run_job() has already
    returned 202. Callers poll GET /jobs/{job_id} to see it.
    """
    job_id = uuid4().hex
    _jobs[job_id] = {"status": "pending", "result": None, "error": None, "http_status": None}

    async def _runner() -> None:
        try:
            result = await coro
            _jobs[job_id]["result"] = result
            _jobs[job_id]["status"] = "done"
        except Exception as exc:
            _jobs[job_id]["error"] = str(exc)
            _jobs[job_id]["http_status"] = classify_job_exception(exc)
            _jobs[job_id]["status"] = "failed"

    asyncio.create_task(_runner())
    return job_id
