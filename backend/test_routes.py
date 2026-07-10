"""Tests for the backend HTTP layer around StudyPlanFlow.

No real LLM calls: crewai.agent.core.Agent.execute_task is monkeypatched to
return a canned JSON string matching whatever Task.output_pydantic expects
(SyllabusDraft / CalendarStructure / StudyPlan / QuizSet / PlanRevision),
dispatched purely on that type. This still runs the REAL Task/Crew/guardrail
machinery (Task._export_output's JSON parsing, and every guardrail in
crews/*/guardrails.py) against the canned output — the project has no prior
Crew-mocking pattern to follow (all existing testing used Crew.test()
against real LLM calls), so this establishes one at the lowest boundary
that still exercises real guardrail logic, including the real
guardrail-exhaustion exception when a canned output is deliberately made to
fail validation.

/plan takes raw text per subject now (there is no separate "already
structured" input path — see backend/routes.py's module docstring): every
subject is converted via SyllabusExtractorCrew before StudyPlanFlow ever
sees it. RAW_SUBJECTS below is the request body shape; _SYLLABUS_DRAFT is
the canned extractor output the mocked Agent.execute_task returns for it.

Fixture shape: one subject ("TestSubject"), one unit, one topic
("TestTopic"), no sub-topics, and a 5-day/2h-per-day calendar with no
exams/deadlines/gaps — this makes allocate_days_to_subjects's output fully
deterministic (every day goes to the only subject) and easy to satisfy
in the canned outputs' guardrails.
"""

import asyncio
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import jobs, registry, tokens
from backend.app import app
from backend.tokens import issue_token
from crewai_core.crews.academic_planner.scheduling import allocate_days_to_subjects
from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.plan_revision import PlanRevision
from crewai_core.models.quiz import QuizQuestion, QuizSet
from crewai_core.models.quiz_attempt import QuestionAnswer, QuizAttempt
from crewai_core.models.study_plan import DayPlan, EntryStatus, StudyPlan, StudyPlanEntry
from crewai_core.models.syllabus import SyllabusStructure, SyllabusTopic, SyllabusUnit
from crewai_core.models.syllabus_draft import SyllabusDraft
from crewai_core.models.weak_topic import TopicStatus

SUBJECT = "TestSubject"
TOPIC = "TestTopic"

RAW_SUBJECTS = [
    {
        "subject_name": SUBJECT,
        "grade": "10",
        "raw_index_text": "UnitA (100%)\n  TestTopic",
    }
]

RAW_SYLLABI = [
    {
        "grade": "10",
        "subject": SUBJECT,
        "units": [
            {
                "unit_name": "UnitA",
                "weightage_percent": 100,
                "topics": [{"topic_name": TOPIC, "sub_topics": []}],
            }
        ],
    }
]

RAW_CALENDAR = {
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

_SYLLABUS_STRUCTURE = SyllabusStructure(
    grade="10",
    subject=SUBJECT,
    units=[SyllabusUnit(unit_name="UnitA", weightage_percent=100, topics=[SyllabusTopic(topic_name=TOPIC, sub_topics=[])])],
)
_CALENDAR_STRUCTURE = CalendarStructure.model_validate(RAW_CALENDAR)
_DAY_BUDGET = allocate_days_to_subjects(_CALENDAR_STRUCTURE, [_SYLLABUS_STRUCTURE])[SUBJECT]

# What the mocked SyllabusExtractorCrew task returns for RAW_SUBJECTS[0] —
# the one and only conversion step /plan now runs on every subject's raw
# text before handing it to StudyPlanFlow.
_SYLLABUS_DRAFT = SyllabusDraft.model_validate(
    {
        "grade": "10",
        "subject": SUBJECT,
        "units": [
            {
                "unit_name": "UnitA",
                "weightage_percent": 100,
                "weightage_is_estimated": False,
                "topics": [
                    {"topic_name": TOPIC, "sub_topics": [], "source_confidence": "matched"}
                ],
            }
        ],
        "subject_mismatch": False,
        "subject_mismatch_reason": None,
    }
)

# subject_mismatch=True -> _convert_subject's SyllabusExtractorCrew
# guardrail hard-rejects on every retry, so the /plan job fails for this
# student rather than silently building a plan from unrelated text.
_MISMATCHED_SYLLABUS_DRAFT = SyllabusDraft.model_validate(
    {
        "grade": "10",
        "subject": SUBJECT,
        "units": [],
        "subject_mismatch": True,
        "subject_mismatch_reason": "Source text is unrelated to the declared subject.",
    }
)

# A valid StudyPlan covering every budgeted day with the one real topic,
# never exceeding that day's budgeted hours -> passes the Plan Generator
# guardrail (full topic coverage, no invented topics/days, no hour overrun).
_VALID_STUDY_PLAN = StudyPlan(
    days=[
        DayPlan(date=day, entries=[StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC, hours_allocated=hours)])
        for day, hours in _DAY_BUDGET
    ]
)

# Deliberately invented topic name -> fails the Plan Generator guardrail
# ("not present in ...'s syllabus") on every retry, so Task exhausts
# guardrail_max_retries and raises the real bare Exception this project
# maps to 502.
_INVALID_STUDY_PLAN = StudyPlan(
    days=[
        DayPlan(
            date=_DAY_BUDGET[0][0],
            entries=[StudyPlanEntry(subject=SUBJECT, topic_name="Not A Real Topic", hours_allocated=0.5)],
        )
    ]
)


def _fake_execute_task(monkeypatch, *, study_plan=None, syllabus_draft=None):
    """Patch Agent.execute_task to return canned JSON dispatched purely on
    task.output_pydantic, so every crew's real Task/guardrail machinery
    still runs against it. study_plan overrides the StudyPlan case (used to
    force a guardrail-exhaustion failure in specific tests). syllabus_draft
    overrides the SyllabusDraft case (used to force the extractor's
    subject_mismatch guardrail rejection in specific tests).
    """
    plan_to_use = study_plan or _VALID_STUDY_PLAN
    draft_to_use = syllabus_draft or _SYLLABUS_DRAFT

    def fake(self, task, context=None, tools=None):
        model = task.output_pydantic
        if model is SyllabusDraft:
            return draft_to_use.model_dump_json()
        if model is CalendarStructure:
            return _CALENDAR_STRUCTURE.model_dump_json()
        if model is StudyPlan:
            return plan_to_use.model_dump_json()
        if model is QuizSet:
            # Derive subject/topic from the interpolated task description
            # rather than assuming a fixed pair, so the unknown-topic test
            # (which requests a topic outside the syllabus) still gets a
            # QuizSet shaped to match what was actually requested.
            return QuizSet(
                subject=SUBJECT,
                topic_name=_requested_topic_name(task),
                questions=[
                    QuizQuestion(
                        subject=SUBJECT,
                        topic_name=_requested_topic_name(task),
                        question_text=f"Q{i}?",
                        options=["A", "B", "C", "D"],
                        correct_option_index=0,
                    )
                    for i in range(15)
                ],
            ).model_dump_json()
        if model is PlanRevision:
            # The optimizer's guardrail only allows dates that are actually
            # in remaining_days (>= real wall-clock today — see
            # flow.py's split_remaining_days), so this can't reuse the
            # full _DAY_BUDGET range unconditionally: any budgeted day
            # before today would fail "not one of the original remaining
            # days". Only emit days >= today.
            today = date.today().isoformat()
            return PlanRevision(
                days=[
                    DayPlan(date=day, entries=[StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC, hours_allocated=hours)])
                    for day, hours in _DAY_BUDGET
                    if day >= today
                ]
            ).model_dump_json()
        raise AssertionError(f"Unexpected output_pydantic type in test mock: {model}")

    monkeypatch.setattr("crewai.agent.core.Agent.execute_task", fake)


def _requested_topic_name(task) -> str:
    # The AssessmentDesigner task's interpolated description embeds the
    # exact requested topic name after "on ONLY the topic: ".
    marker = "on ONLY the topic: "
    idx = task.description.index(marker) + len(marker)
    return task.description[idx:].split(".", 1)[0].split(",", 1)[0].strip().strip('"')


@pytest.fixture(autouse=True)
def _clear_state():
    registry._registry.clear()
    jobs._jobs.clear()
    yield
    registry._registry.clear()
    jobs._jobs.clear()


@pytest.fixture
def client():
    # Used as a context manager (not just constructed) so the ASGI app's
    # event loop stays alive across requests within the test — background
    # jobs use asyncio.create_task, which needs the loop that scheduled it
    # to keep running for the task to ever execute. A plain (non-context-
    # manager) TestClient spins up and tears down a fresh loop PER REQUEST,
    # which silently orphans any asyncio.create_task before it can run —
    # confirmed directly by reproducing that exact hang.
    with TestClient(app) as c:
        yield c


def _auth_headers(student_id: str) -> dict[str, str]:
    """A valid, correctly-signed Authorization header asserting student_id —
    threaded into every existing HTTP call in this file that hits a
    /students/{id}/... route now that backend.auth.require_owner enforces
    token ownership on all of them (Step 5)."""
    return {"Authorization": f"Bearer {issue_token(student_id)}"}


def _wait_for_job(client, job_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] != "pending":
            return body
        time.sleep(0.02)
    raise TimeoutError(f"job {job_id} did not finish in {timeout}s")


def _create_plan(client, student_id="student-1", subjects=None):
    resp = client.post(
        f"/students/{student_id}/plan",
        json={"subjects": subjects or RAW_SUBJECTS, "raw_calendar": RAW_CALENDAR},
        headers=_auth_headers(student_id),
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    return _wait_for_job(client, job_id)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_issue_token_endpoint_returns_valid_token(client):
    resp = client.post("/auth/token", json={"student_id": "some-id"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["student_id"] == "some-id"
    assert tokens.verify_token(body["token"]) == "some-id"


def test_create_and_get_plan_happy_path(client, monkeypatch):
    _fake_execute_task(monkeypatch)
    job = _create_plan(client)
    assert job["status"] == "done"

    resp = client.get("/students/student-1/plan", headers=_auth_headers("student-1"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert len(body["study_plan"]["days"]) == len(_DAY_BUDGET)


def test_get_plan_not_ready_before_job_completes(client):
    # Registered directly via the registry (bypassing /plan) with
    # kickoff_async() never called, so state.study_plan is still None —
    # exactly the state a real /plan job is in before it completes. This
    # is deterministic, unlike racing a real in-flight background job
    # against TestClient's single-threaded ASGI portal, where wall-clock
    # timing between the POST and the immediate GET isn't reliable (a
    # sync delay inside the mocked crew call was observed to make the
    # POST/GET calls themselves block rather than truly running the job
    # in the background, since TestClient drives everything off one
    # event-loop thread).
    registry.create_or_replace("student-2", RAW_SYLLABI, RAW_CALENDAR)
    resp2 = client.get("/students/student-2/plan", headers=_auth_headers("student-2"))
    assert resp2.status_code == 200
    assert resp2.json()["ready"] is False


def test_get_plan_unknown_student_404(client):
    # A valid, correctly-signed token for "nobody" is required here so the
    # request clears the ownership check and reaches the real "unknown
    # student in registry" 404 path — without it this would incorrectly get
    # 401 instead, testing the wrong thing.
    resp = client.get("/students/nobody/plan", headers=_auth_headers("nobody"))
    assert resp.status_code == 404


def test_get_plan_survives_registry_clear_simulating_restart(client, monkeypatch):
    """Step 2 regression: registry.get()'s SQLite rehydration fallback
    means clearing the in-memory registry (simulating a backend process
    restart) must NOT turn an existing student's plan into a 404 — the
    real @persist() SQLite row backing this Flow is still on disk."""
    _fake_execute_task(monkeypatch)
    job = _create_plan(client)
    assert job["status"] == "done"

    resp_before = client.get("/students/student-1/plan", headers=_auth_headers("student-1"))
    assert resp_before.status_code == 200
    body_before = resp_before.json()

    # Simulate a process restart: only the in-memory dict is lost.
    registry._registry.clear()

    resp_after = client.get("/students/student-1/plan", headers=_auth_headers("student-1"))
    assert resp_after.status_code == 200
    body_after = resp_after.json()
    assert body_after["ready"] is True
    assert body_after["study_plan"] == body_before["study_plan"]


def test_get_job_unknown_404(client):
    resp = client.get("/jobs/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /students/{id}/plan/entries — set_entry_status
# ---------------------------------------------------------------------------


def _create_plan_with_entry(student_id: str, status=None):
    """Build a Flow directly via the registry with a known single-entry
    study plan, bypassing /plan and any Crew calls — same pattern as
    _create_plan_without_llm, since this route needs no LLM involvement."""
    flow, lock = registry.create_or_replace(student_id, RAW_SYLLABI, RAW_CALENDAR)
    entry_kwargs = {"subject": SUBJECT, "topic_name": TOPIC, "hours_allocated": 2.0}
    if status is not None:
        entry_kwargs["status"] = status
    flow.state.study_plan = StudyPlan(
        days=[DayPlan(date="2026-07-10", entries=[StudyPlanEntry(**entry_kwargs)])]
    )
    return flow, lock


def test_set_entry_status_happy_path_full_cycle(client):
    _create_plan_with_entry("student-status")

    for target_status in ("in_progress", "completed", "not_started"):
        resp = client.patch(
            "/students/student-status/plan/entries",
            json={"date": "2026-07-10", "subject": SUBJECT, "topic_name": TOPIC, "status": target_status},
            headers=_auth_headers("student-status"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == target_status

    flow, _ = registry.get("student-status")
    assert flow.state.study_plan.days[0].entries[0].status == EntryStatus.NOT_STARTED


def test_set_entry_status_unknown_student_404(client):
    resp = client.patch(
        "/students/nobody/plan/entries",
        json={"date": "2026-07-10", "subject": SUBJECT, "topic_name": TOPIC, "status": "completed"},
        headers=_auth_headers("nobody"),
    )
    assert resp.status_code == 404


def test_set_entry_status_unknown_entry_422(client):
    _create_plan_with_entry("student-status-2")

    resp = client.patch(
        "/students/student-status-2/plan/entries",
        json={"date": "2026-07-10", "subject": SUBJECT, "topic_name": "Not A Real Topic", "status": "completed"},
        headers=_auth_headers("student-status-2"),
    )
    assert resp.status_code == 422


def test_set_entry_status_before_plan_ready_422(client):
    # Registered but state.study_plan is still None — no plan generated yet.
    registry.create_or_replace("student-status-3", RAW_SYLLABI, RAW_CALENDAR)

    resp = client.patch(
        "/students/student-status-3/plan/entries",
        json={"date": "2026-07-10", "subject": SUBJECT, "topic_name": TOPIC, "status": "completed"},
        headers=_auth_headers("student-status-3"),
    )
    assert resp.status_code == 422


def test_set_entry_status_does_not_affect_sibling_entries(client):
    flow, _ = registry.create_or_replace("student-status-4", RAW_SYLLABI, RAW_CALENDAR)
    flow.state.study_plan = StudyPlan(
        days=[
            DayPlan(
                date="2026-07-10",
                entries=[
                    StudyPlanEntry(subject=SUBJECT, topic_name=TOPIC, hours_allocated=1.0),
                    StudyPlanEntry(subject=SUBJECT, topic_name="Other Topic", hours_allocated=1.0),
                ],
            ),
        ]
    )

    resp = client.patch(
        "/students/student-status-4/plan/entries",
        json={"date": "2026-07-10", "subject": SUBJECT, "topic_name": TOPIC, "status": "completed"},
        headers=_auth_headers("student-status-4"),
    )
    assert resp.status_code == 200

    entries = flow.state.study_plan.days[0].entries
    assert entries[0].status == EntryStatus.COMPLETED
    assert entries[1].status == EntryStatus.NOT_STARTED  # untouched sibling


def test_quiz_happy_path(client, monkeypatch):
    _fake_execute_task(monkeypatch)
    _create_plan(client)

    resp = client.post(
        "/students/student-1/quiz",
        json={"subject": SUBJECT, "topic": TOPIC},
        headers=_auth_headers("student-1"),
    )
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "done"
    assert job["result"]["subject"] == SUBJECT
    assert job["result"]["topic_name"] == TOPIC
    assert 15 <= len(job["result"]["questions"]) <= 25


def test_wellbeing_check_does_not_block(client):
    """Regression test for @human_feedback removal: this must return
    promptly, not hang on a console input() call. Asserted via a wall-clock
    bound on the call itself (TestClient's per-call `timeout` kwarg is
    deprecated) — if @human_feedback's blocking input() prompt were still
    wired in here, this call would hang indefinitely rather than return
    quickly."""
    _create_plan_without_llm("student-wb")
    start = time.time()
    resp = client.post("/students/student-wb/wellbeing-check", headers=_auth_headers("student-wb"))
    elapsed = time.time() - start
    assert resp.status_code == 200
    assert elapsed < 5.0


def test_wellbeing_check_returns_empty_list_when_nothing_warranted(client):
    _create_plan_without_llm("student-wb-empty")
    resp = client.post("/students/student-wb-empty/wellbeing-check", headers=_auth_headers("student-wb-empty"))
    assert resp.status_code == 200
    assert resp.json() == []


def test_wellbeing_check_returns_list_with_quiz_inactivity_flag(client):
    _create_plan_without_llm("student-wb-quiz", backdate_days=10)
    resp = client.post("/students/student-wb-quiz/wellbeing-check", headers=_auth_headers("student-wb-quiz"))
    assert resp.status_code == 200
    flags = resp.json()
    assert len(flags) == 1
    assert flags[0]["days_since_last_activity"] == 10


def test_wellbeing_check_returns_both_flags_when_both_conditions_met(client):
    """Task 5: quiz inactivity and missed-day streak are independent — both
    can fire in the same call. Seeds a Flow with 10-day-stale quiz history
    AND a study_plan with a missed-day streak past MISSED_DAYS_THRESHOLD."""
    from crewai_core.models.study_plan import DayPlan, EntryStatus, StudyPlan, StudyPlanEntry
    from crewai_core.wellbeing_monitor import MISSED_DAYS_THRESHOLD

    flow, _ = _create_plan_without_llm("student-wb-both", backdate_days=10)
    today = date.today()
    missed_dates = [(today - timedelta(days=i)).isoformat() for i in range(1, MISSED_DAYS_THRESHOLD + 1)]
    flow.state.study_plan = StudyPlan(
        days=[
            DayPlan(
                date=d,
                entries=[
                    StudyPlanEntry(
                        subject=SUBJECT, topic_name=TOPIC, hours_allocated=1.0,
                        status=EntryStatus.NOT_STARTED,
                    )
                ],
            )
            for d in missed_dates
        ]
    )

    resp = client.post("/students/student-wb-both/wellbeing-check", headers=_auth_headers("student-wb-both"))
    assert resp.status_code == 200
    flags = resp.json()
    assert len(flags) == 2


def test_wellbeing_ack_lifecycle(client):
    flow, _ = _create_plan_without_llm("student-wb2", backdate_days=10)

    resp = client.post("/students/student-wb2/wellbeing-check", headers=_auth_headers("student-wb2"))
    assert resp.status_code == 200
    flags = resp.json()
    assert len(flags) == 1
    flag = flags[0]
    assert flag["acknowledged"] is False

    ack_resp = client.post(
        "/students/student-wb2/wellbeing-ack",
        json={"flag_id": flag["id"], "reviewer_note": "Looked into it, all good."},
        headers=_auth_headers("student-wb2"),
    )
    assert ack_resp.status_code == 200
    acked = ack_resp.json()
    assert acked["acknowledged"] is True
    assert acked["reviewer_note"] == "Looked into it, all good."

    missing_resp = client.post(
        "/students/student-wb2/wellbeing-ack",
        json={"flag_id": "does-not-exist", "reviewer_note": "n/a"},
        headers=_auth_headers("student-wb2"),
    )
    assert missing_resp.status_code == 404


def _create_plan_without_llm(student_id: str, backdate_days: int | None = None):
    """Build a Flow directly via the registry (bypassing the /plan route
    and any Crew calls) purely to get quiz_history in a known state for the
    wellbeing tests, which don't need syllabi/calendar analysis at all."""
    flow, lock = registry.create_or_replace(student_id, RAW_SYLLABI, RAW_CALENDAR)
    if backdate_days is not None:
        attempted_at = (date.today() - timedelta(days=backdate_days)).isoformat()
        flow.state.quiz_history.append(
            QuizAttempt(
                subject=SUBJECT,
                topic_name=TOPIC,
                attempted_at=attempted_at,
                answers=[
                    QuestionAnswer(
                        question_text="q",
                        selected_option_index=0,
                        correct=True,
                        response_time_seconds=10.0,
                        retries=0,
                    )
                ],
            )
        )
    return flow, lock


# ---------------------------------------------------------------------------
# /attempts + plan_optimizer_triggered
# ---------------------------------------------------------------------------


def _build_attempt(subject, topic, accuracy, n=20):
    correct_count = round(n * accuracy)
    answers = [
        QuestionAnswer(
            question_text=f"q{i}",
            selected_option_index=0,
            correct=i < correct_count,
            response_time_seconds=15.0 if i < correct_count else 45.0,
            retries=0,
        )
        for i in range(n)
    ]
    return QuizAttempt(subject=subject, topic_name=topic, answers=answers)


def test_attempts_reports_plan_optimizer_triggered_true_when_struggling(client, monkeypatch):
    _fake_execute_task(monkeypatch)
    _create_plan(client)

    attempt = _build_attempt(SUBJECT, TOPIC, accuracy=0.2)  # well below Struggling cutoff
    resp = client.post(
        "/students/student-1/attempts", json=attempt.model_dump(), headers=_auth_headers("student-1")
    )
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "done"
    assert job["result"]["weak_topic_update"]["status"] == TopicStatus.STRUGGLING.value
    assert job["result"]["plan_optimizer_triggered"] is True


def test_attempts_reports_plan_optimizer_triggered_false_when_mastered(client, monkeypatch):
    _fake_execute_task(monkeypatch)
    _create_plan(client)

    attempt = _build_attempt(SUBJECT, TOPIC, accuracy=1.0)  # Mastered
    resp = client.post(
        "/students/student-1/attempts", json=attempt.model_dump(), headers=_auth_headers("student-1")
    )
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "done"
    assert job["result"]["weak_topic_update"]["status"] == TopicStatus.MASTERED.value
    assert job["result"]["plan_optimizer_triggered"] is False


# ---------------------------------------------------------------------------
# Plan replacement discards prior state
# ---------------------------------------------------------------------------


def test_second_plan_call_discards_prior_quiz_history(client, monkeypatch):
    _fake_execute_task(monkeypatch)
    _create_plan(client)

    attempt = _build_attempt(SUBJECT, TOPIC, accuracy=1.0)
    resp = client.post(
        "/students/student-1/attempts", json=attempt.model_dump(), headers=_auth_headers("student-1")
    )
    job = _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "done"

    flow_before, _ = registry.get("student-1")
    assert len(flow_before.state.quiz_history) == 1

    # Second /plan call for the same student_id.
    _create_plan(client)

    flow_after, _ = registry.get("student-1")
    assert flow_after is not flow_before
    assert len(flow_after.state.quiz_history) == 0


# ---------------------------------------------------------------------------
# Concurrency: the per-student lock actually serializes
# ---------------------------------------------------------------------------


def test_lock_serializes_two_requests_for_same_student(monkeypatch):
    """Prove the lock is held for the full duration of an operation: start
    a slow first job, then immediately try a second lock-holding operation
    and assert it doesn't proceed until the first releases the lock."""
    events: list[str] = []

    async def slow_kickoff(self):
        events.append("first-start")
        await asyncio.sleep(0.2)
        events.append("first-end")
        self.state.study_plan = _VALID_STUDY_PLAN

    async def scenario():
        flow, lock = registry.create_or_replace("student-lock", RAW_SYLLABI, RAW_CALENDAR)
        monkeypatch.setattr(flow, "kickoff_async", slow_kickoff.__get__(flow))

        async def first():
            async with lock:
                await flow.kickoff_async()

        async def second():
            # Wait long enough that `first` has definitely started but not
            # finished (it sleeps 0.2s), then try to acquire the same lock.
            await asyncio.sleep(0.05)
            events.append("second-tries-lock")
            async with lock:
                events.append("second-acquired")

        await asyncio.gather(first(), second())

    asyncio.run(scenario())

    # second must not acquire the lock until AFTER first releases it
    # (i.e. after "first-end"), proving the lock genuinely serializes.
    assert events.index("second-tries-lock") < events.index("first-end")
    assert events.index("second-acquired") > events.index("first-end")


# ---------------------------------------------------------------------------
# Guardrail exhaustion -> 502
# ---------------------------------------------------------------------------


def test_plan_generation_guardrail_exhaustion_returns_502(client, monkeypatch):
    _fake_execute_task(monkeypatch, study_plan=_INVALID_STUDY_PLAN)

    resp = client.post(
        "/students/student-bad-plan/plan",
        json={"subjects": RAW_SUBJECTS, "raw_calendar": RAW_CALENDAR},
        headers=_auth_headers("student-bad-plan"),
    )
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "failed"
    assert job["http_status"] == 502
    assert "validation" in job["error"].lower() or "retries" in job["error"].lower()


def test_plan_creation_rejects_mismatched_subject_text_returns_502(client, monkeypatch):
    """The one conversion step (SyllabusExtractorCrew) hard-rejects text
    that doesn't match its declared subject — the whole /plan job fails for
    that student rather than silently building a plan from unrelated text.
    """
    _fake_execute_task(monkeypatch, syllabus_draft=_MISMATCHED_SYLLABUS_DRAFT)

    resp = client.post(
        "/students/student-mismatch/plan",
        json={"subjects": RAW_SUBJECTS, "raw_calendar": RAW_CALENDAR},
        headers=_auth_headers("student-mismatch"),
    )
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "failed"
    assert job["http_status"] == 502


def test_quiz_unknown_topic_guardrail_exhaustion_returns_502(client, monkeypatch):
    _fake_execute_task(monkeypatch)
    _create_plan(client)

    resp = client.post(
        "/students/student-1/quiz",
        json={"subject": SUBJECT, "topic": "Not A Real Topic"},
        headers=_auth_headers("student-1"),
    )
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "failed"
    assert job["http_status"] == 502


# ---------------------------------------------------------------------------
# /quiz error mapping: unknown subject (422), before /plan completes (409)
# ---------------------------------------------------------------------------


def test_quiz_unknown_subject_returns_422(client, monkeypatch):
    _fake_execute_task(monkeypatch)
    _create_plan(client)

    resp = client.post(
        "/students/student-1/quiz",
        json={"subject": "NotASubject", "topic": TOPIC},
        headers=_auth_headers("student-1"),
    )
    assert resp.status_code == 202
    job = _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "failed"
    assert job["http_status"] == 422


def test_quiz_before_plan_job_completes_returns_409(client, monkeypatch):
    # A registered Flow (so the student isn't 404) that has never had
    # kickoff_async() run at all, i.e. state.syllabi is still empty —
    # generate_quiz()'s own RuntimeError check. Note this can't be
    # reproduced by racing a real /plan job: /quiz shares that student's
    # lock, so it would simply queue behind (and only run after) any
    # in-flight /plan kickoff, which by construction populates
    # state.syllabi before releasing the lock. The only way state.syllabi
    # is empty when generate_quiz() runs is if kickoff_async() was never
    # started for this Flow instance in the first place.
    _fake_execute_task(monkeypatch)
    registry.create_or_replace("student-slow", RAW_SYLLABI, RAW_CALENDAR)

    quiz_resp = client.post(
        "/students/student-slow/quiz",
        json={"subject": SUBJECT, "topic": TOPIC},
        headers=_auth_headers("student-slow"),
    )
    assert quiz_resp.status_code == 202
    job = _wait_for_job(client, quiz_resp.json()["job_id"])
    assert job["status"] == "failed"
    assert job["http_status"] == 409


# ---------------------------------------------------------------------------
# Step 5: ownership enforcement (backend.auth.require_owner)
# ---------------------------------------------------------------------------


def test_no_authorization_header_returns_401(client):
    resp = client.get("/students/student-1/plan")
    assert resp.status_code == 401


def test_malformed_authorization_header_returns_401(client):
    resp = client.get(
        "/students/student-1/plan",
        headers={"Authorization": "NotBearer sometoken"},
    )
    assert resp.status_code == 401


def test_garbage_token_returns_401(client):
    resp = client.get(
        "/students/student-1/plan",
        headers={"Authorization": "Bearer this-is-not-a-real-token"},
    )
    assert resp.status_code == 401


def test_valid_token_for_different_student_returns_403(client):
    """The single most important test in this suite: a correctly-signed
    token issued for student "A" must not grant access to student "B"'s
    route — this is the literal cross-student-access scenario Step 5 exists
    to prevent."""
    resp = client.get(
        "/students/student-b/plan",
        headers=_auth_headers("student-a"),
    )
    assert resp.status_code == 403


def test_tampered_token_with_swapped_student_id_returns_401(client):
    """A token issued for one student, with its payload decoded/modified to
    claim a DIFFERENT student_id but the ORIGINAL signature bytes left
    unchanged, must fail signature verification (401) — proving the HMAC
    actually protects the payload from being silently swapped, not just
    that some signature is present."""
    token = issue_token("student-a")
    payload_segment, signature_segment = token.split(".")

    import base64
    import json

    def _b64url_decode(text: str) -> bytes:
        padded = text + "=" * (-len(text) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    payload = json.loads(_b64url_decode(payload_segment))
    payload["student_id"] = "student-b"
    tampered_payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    tampered_token = f"{tampered_payload_segment}.{signature_segment}"

    resp = client.get(
        "/students/student-b/plan",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    assert resp.status_code == 401
