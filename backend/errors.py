"""Exception -> HTTP mapping for the backend routes.

Guardrail-exhaustion exception type, confirmed by direct reproduction
(not guessed from docs/memory): crewai's installed Task._invoke_guardrail_function
/ _ainvoke_guardrail_function (crewai/task.py) raises a BARE `Exception`
(type(e) is Exception, MRO is [Exception, BaseException, object] — there is
no dedicated GuardrailValidationError class in this installed crewai
version, 1.14.4) once guardrail_max_retries is exhausted, with message
"Task failed {guardrail_name} validation after {N} retries. Last error:
{guardrail_result.error}". Reproduced live via a forced-failing guardrail
run through Crew.kickoff_async() with the agent's execute_task mocked out
(see the one-off repro script used to verify this; not checked into the
repo).

Because CrewAI does not give this its own exception class, we cannot catch
by type alone (a bare `except Exception` would also swallow unrelated
bugs). is_guardrail_exhaustion() below matches on the exact bare-Exception
type PLUS the distinctive message substrings from that f-string, which is
as precise as this crewai version allows.
"""

from fastapi import HTTPException


def is_guardrail_exhaustion(exc: BaseException) -> bool:
    if type(exc) is not Exception:
        return False
    message = str(exc)
    return "guardrail" in message and "retries" in message and "validation after" in message


def student_not_found_error(student_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No student found with id '{student_id}'.")


def job_not_found_error(job_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No job found with id '{job_id}'.")


def ownership_mismatch_error(student_id: str) -> HTTPException:
    """403 — the request's verified token asserts a DIFFERENT student_id
    than the one in this route's own path (see backend/auth.py's
    require_owner). Distinct from student_not_found_error (404, genuinely
    unknown student) and from a 401 (missing/malformed/unverifiable token,
    constructed directly in backend/auth.py since there's no existing 401
    helper here to reuse) — this is a valid token that simply doesn't own
    the resource its own request is addressing."""
    return HTTPException(
        status_code=403,
        detail=f"Token does not grant access to student '{student_id}'.",
    )


def classify_job_exception(exc: BaseException) -> int:
    """Map an exception raised inside a background job's coroutine to an
    HTTP status code, stored on the job record for GET /jobs/{job_id} to
    report (the exception happens after the originating POST already
    returned 202, so it can't be raised as an HTTPException there).

    - ValueError (e.g. flow.generate_quiz's unknown-subject check) -> 422.
    - RuntimeError (e.g. flow.generate_quiz called before syllabi analyzed)
      -> 409.
    - Guardrail-exhaustion (e.g. flow.generate_quiz's unknown-topic path,
      or plan/optimizer generation failing validation after retries) -> 502.
    - Anything else -> 500.
    """
    if is_guardrail_exhaustion(exc):
        return 502
    if isinstance(exc, ValueError):
        return 422
    if isinstance(exc, RuntimeError):
        return 409
    return 500
