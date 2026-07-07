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

/plan takes each subject as raw text (however the student typed/pasted it —
there is no separate "already structured" input shape) and converts it via
SyllabusExtractorCrew before handing the result to StudyPlanFlow. One path:
raw text in, syllabus out, straight into the Flow — no draft, no review
step, no confirm step. If a subject's text is unrelated to its declared
subject_name or isn't a syllabus at all, the extractor's guardrail rejects
it and the whole /plan job fails for that student (see
backend.errors.classify_job_exception's 502 mapping) rather than silently
building a plan from garbage.

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
from crewai_core.crews.syllabus_extractor.crew import SyllabusExtractorCrew
from crewai_core.models.quiz_attempt import QuizAttempt
from crewai_core.models.study_plan import EntryStatus
from crewai_core.models.syllabus import SyllabusStructure, SyllabusTopic, SyllabusUnit
from crewai_core.models.syllabus_draft import SyllabusDraft

router = APIRouter()


class RawSubjectSyllabus(BaseModel):
    """One subject's syllabus exactly as the student typed/pasted it in —
    plain text, any layout, any level of organization. There is no separate
    "already structured" input shape; every subject goes through the same
    conversion step (see _convert_subject below) on the way into the plan."""

    subject_name: str
    grade: str
    raw_index_text: str


class CreatePlanRequest(BaseModel):
    subjects: list[RawSubjectSyllabus]
    raw_calendar: dict


class QuizRequest(BaseModel):
    subject: str
    topic: str


class WellbeingAckRequest(BaseModel):
    flag_id: str
    reviewer_note: str


class SetEntryStatusRequest(BaseModel):
    date: str
    subject: str
    topic_name: str
    status: EntryStatus


def _get_flow_and_lock(student_id: str):
    entry = registry.get(student_id)
    if entry is None:
        raise student_not_found_error(student_id)
    return entry


async def _convert_subject(subject: RawSubjectSyllabus) -> SyllabusStructure:
    """The one conversion step: raw text in, a clean SyllabusStructure out.
    Runs SyllabusExtractorCrew's guardrail-checked extraction; if the text
    is unrelated to subject_name or isn't a syllabus at all, this raises
    (the crew's guardrail rejects it and retries are exhausted) and the
    whole /plan request fails for this student rather than silently
    building a plan from garbage. No draft, no review step, no separate
    path for input that happens to already look organized — every subject
    goes through this same conversion on the way to StudyPlanFlow.

    The result is handed to StudyPlanFlow as pre_analyzed_syllabi, NOT run
    through SyllabusAnalystCrew inside the Flow — re-running that crew on
    data this conversion already produced clean wouldn't validate
    anything real (its guardrail would just compare the output back
    against the same input it started from)."""

    crew_instance = SyllabusExtractorCrew(
        subject_name=subject.subject_name,
        grade=subject.grade,
        raw_index_text=subject.raw_index_text,
    )
    result = await crew_instance.crew().kickoff_async(
        inputs={
            "subject_name": crew_instance.subject_name,
            "grade": crew_instance.grade,
            "raw_index_text": crew_instance.raw_index_text,
        }
    )
    draft: SyllabusDraft = result.pydantic
    return SyllabusStructure(
        grade=draft.grade,
        subject=draft.subject,
        units=[
            SyllabusUnit(
                unit_name=unit.unit_name,
                weightage_percent=unit.weightage_percent,
                topics=[
                    SyllabusTopic(topic_name=topic.topic_name, sub_topics=list(topic.sub_topics))
                    for topic in unit.topics
                ],
            )
            for unit in draft.units
        ],
    )


@router.post("/students/{student_id}/plan", status_code=202)
async def create_plan(student_id: str, body: CreatePlanRequest) -> dict[str, str]:
    """Converts every subject's raw text straight into a syllabus, then
    kicks off the Flow — one path, no intermediate draft/review/confirm
    step, and no redundant second AI pass through SyllabusAnalystCrew
    inside the Flow (see registry.create_or_replace's pre_analyzed_syllabi).
    Runs as a background job (same pattern as /quiz, /attempts) since both
    the conversion and the Flow itself are LLM-call-length; poll
    GET /jobs/{job_id} for the result."""

    async def _convert_then_kickoff() -> dict[str, Any] | None:
        syllabi = [await _convert_subject(subject) for subject in body.subjects]
        raw_syllabi = [s.model_dump() for s in syllabi]
        flow, lock = registry.create_or_replace(
            student_id, raw_syllabi, body.raw_calendar, pre_analyzed_syllabi=syllabi
        )
        async with lock:
            await flow.kickoff_async()
            return flow.state.study_plan.model_dump() if flow.state.study_plan else None

    job_id = jobs.run_job(_convert_then_kickoff())
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


@router.patch("/students/{student_id}/plan/entries")
async def set_entry_status(student_id: str, body: SetEntryStatusRequest) -> dict[str, Any]:
    """Toggle one study-plan entry's status (not_started/in_progress/
    completed — never "missed", which is derived read-side only, see
    crewai_core/entry_status.py). Plain, synchronous, deterministic — same
    category as /wellbeing-check and /wellbeing-ack, NOT job-polled like
    /plan, /quiz, /attempts, since no LLM call is involved.

    404 if no Flow exists yet for student_id. 422 if the study plan isn't
    ready yet, or no entry matches the given (date, subject, topic_name)
    triple — StudyPlanFlow.set_entry_status() raises ValueError for both,
    mapped directly to 422 here since this route isn't job-polled (compare
    backend.errors.classify_job_exception's async equivalent for /quiz)."""
    flow, lock = _get_flow_and_lock(student_id)
    async with lock:
        try:
            updated_entry = flow.set_entry_status(
                body.date, body.subject, body.topic_name, body.status
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return updated_entry.model_dump(mode="json")


@router.get("/students/{student_id}/syllabi")
async def get_syllabi(student_id: str) -> list[dict[str, Any]]:
    """The per-subject SyllabusStructure trees (units -> topics) built for
    this student's plan — the same data StudyPlanFlow.generate_quiz()
    validates a quiz request against. Lets the frontend offer subject/topic
    dropdowns instead of free-text entry, which otherwise only surfaces
    typos as a 422 (unknown subject) or a slow 502 (unknown topic, after
    the guardrail exhausts its retries). 404 if no Flow exists yet for
    student_id (same as GET /plan); returns an empty list (not 404) if the
    Flow exists but /plan hasn't completed yet, since that's a valid,
    momentary state, not an error.
    """
    flow, lock = _get_flow_and_lock(student_id)
    async with lock:
        syllabi = flow.state.syllabi
    return [s.model_dump() for s in syllabi]


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
async def wellbeing_check(student_id: str) -> list[dict[str, Any]]:
    """Runs BOTH wellbeing checks (quiz inactivity, missed-day streak — see
    crewai_core/wellbeing_monitor.py) and returns every flag produced (0,
    1, or 2 — both can genuinely fire in the same call). Was a single
    nullable flag before Task 5 added the second check; callers must now
    handle a list, empty when nothing was warranted."""
    flow, lock = _get_flow_and_lock(student_id)
    async with lock:
        flags = flow.check_wellbeing()
    return [f.model_dump() for f in flags]


@router.post("/students/{student_id}/wellbeing-ack")
async def wellbeing_ack(student_id: str, body: WellbeingAckRequest) -> dict[str, Any]:
    flow, lock = _get_flow_and_lock(student_id)
    async with lock:
        try:
            flag = flow.acknowledge_wellbeing_flag(body.flag_id, body.reviewer_note)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return flag.model_dump()
