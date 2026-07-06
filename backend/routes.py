"""HTTP routes around StudyPlanFlow. See backend/registry.py and
backend/jobs.py for the in-memory student/job stores this module wires
together, and backend/errors.py for the guardrail-exhaustion detection and
HTTP status mapping.

Every operation that touches flow.state (kickoff_async, generate_quiz,
score_attempt, check_wellbeing, acknowledge_wellbeing_flag, and the plain
GET reads of study_plan) is executed while holding that student's
asyncio.Lock for its full duration, per the concurrency requirement — one
student's requests queue against each other; different students never
contend.

/plan, /quiz, /attempts run their Flow operation as a background job
(backend.jobs.run_job) since each can take LLM-call-length time. The
route itself only schedules the job and returns 202 {job_id}; the actual
success/failure (including which HTTP status a failure maps to) is only
knowable once the job's coroutine finishes, so callers read it back via
GET /jobs/{job_id} rather than getting it synchronously from the POST.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import jobs, registry
from backend.errors import job_not_found_error, student_not_found_error
from crewai_core.models.quiz_attempt import QuizAttempt

router = APIRouter()


class CreatePlanRequest(BaseModel):
    raw_syllabi: list[dict]
    raw_calendar: dict


class QuizRequest(BaseModel):
    subject: str
    topic: str


class WellbeingAckRequest(BaseModel):
    flag_id: str
    reviewer_note: str


def _get_flow_and_lock(student_id: str):
    entry = registry.get(student_id)
    if entry is None:
        raise student_not_found_error(student_id)
    return entry


@router.post("/students/{student_id}/plan", status_code=202)
async def create_plan(student_id: str, body: CreatePlanRequest) -> dict[str, str]:
    flow, lock = registry.create_or_replace(student_id, body.raw_syllabi, body.raw_calendar)

    async def _kickoff() -> dict[str, Any] | None:
        async with lock:
            await flow.kickoff_async()
            return flow.state.study_plan.model_dump() if flow.state.study_plan else None

    job_id = jobs.run_job(_kickoff())
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise job_not_found_error(job_id)
    return job


@router.get("/students/{student_id}/plan")
async def get_plan(student_id: str) -> dict[str, Any]:
    """404 if no Flow exists yet for student_id. If the Flow exists but
    study_plan is still None (the /plan job hasn't completed yet), returns
    200 with ready=False instead of a 404 — this is a real Flow in an
    incomplete state, not an unknown student, so it gets a distinct shape
    rather than reusing the "unknown student" 404.
    """
    flow, lock = _get_flow_and_lock(student_id)
    async with lock:
        study_plan = flow.state.study_plan
    if study_plan is None:
        return {"ready": False, "study_plan": None}
    return {"ready": True, "study_plan": study_plan.model_dump()}


@router.post("/students/{student_id}/quiz", status_code=202)
async def create_quiz(student_id: str, body: QuizRequest) -> dict[str, str]:
    flow, lock = _get_flow_and_lock(student_id)

    async def _generate() -> dict[str, Any]:
        async with lock:
            quiz = await flow.generate_quiz(body.subject, body.topic)
            return quiz.model_dump()

    job_id = jobs.run_job(_generate())
    return {"job_id": job_id}


@router.post("/students/{student_id}/attempts", status_code=202)
async def submit_attempt(student_id: str, attempt: QuizAttempt) -> dict[str, str]:
    flow, lock = _get_flow_and_lock(student_id)

    async def _score() -> dict[str, Any]:
        async with lock:
            updated_status = await flow.score_attempt(attempt)
            return {
                "weak_topic_update": updated_status.model_dump(mode="json"),
                "plan_optimizer_triggered": updated_status.status.value == "Struggling",
            }

    job_id = jobs.run_job(_score())
    return {"job_id": job_id}


@router.post("/students/{student_id}/wellbeing-check")
async def wellbeing_check(student_id: str) -> dict[str, Any] | None:
    flow, lock = _get_flow_and_lock(student_id)
    async with lock:
        flag = flow.check_wellbeing()
    return flag.model_dump() if flag is not None else None


@router.post("/students/{student_id}/wellbeing-ack")
async def wellbeing_ack(student_id: str, body: WellbeingAckRequest) -> dict[str, Any]:
    flow, lock = _get_flow_and_lock(student_id)
    async with lock:
        try:
            flag = flow.acknowledge_wellbeing_flag(body.flag_id, body.reviewer_note)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return flag.model_dump()
