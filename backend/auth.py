"""FastAPI dependency enforcing per-student token ownership on every route
that takes a `{student_id}` path param.

This is NOT a login/credential system (see backend/tokens.py and
backend/routes.py's POST /auth/token docstring for the no-account model this
app uses) — it only proves that whoever holds a given token was the one who
minted it for that exact student_id, which stops a request's own URL from
being edited to address a different student than the token was issued for.

Wired per-route via `_owner: str = Depends(require_owner)`, not at the
router level — router-level would break GET /jobs/{job_id} and
POST /auth/token, neither of which has a student_id path param for FastAPI
to resolve.
"""

from fastapi import Header, HTTPException

from backend.errors import ownership_mismatch_error
from backend.tokens import InvalidTokenError, verify_token


def _unauthorized(detail: str) -> HTTPException:
    # No existing 401 helper in backend/errors.py to reuse (that file's
    # existing helpers are all 404s plus classify_job_exception) — 403 is
    # the one case the plan mandates funneling through errors.py, since
    # that's the actual cross-student-access block this feature exists to
    # produce; 401 (missing/malformed/unverifiable credential) is
    # constructed inline here instead.
    return HTTPException(status_code=401, detail=detail)


async def require_owner(student_id: str, authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: extract + verify a Bearer token from the
    Authorization header and confirm it asserts THIS route's student_id.

    - Missing or malformed (no "Bearer " prefix) header -> 401.
    - Token fails signature/shape verification -> 401.
    - Token verifies but names a different student_id than the path param
      -> 403 (the actual ownership check this dependency exists for).

    Returns the verified student_id on success (FastAPI Depends() convention
    — routes don't need the return value beyond satisfying the dependency).
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise _unauthorized("Missing or malformed Authorization header; expected 'Bearer <token>'.")

    token = authorization[len("Bearer ") :]

    try:
        token_student_id = verify_token(token)
    except InvalidTokenError as exc:
        raise _unauthorized(f"Invalid or expired token: {exc}") from exc

    if token_student_id != student_id:
        raise ownership_mismatch_error(student_id)

    return token_student_id
