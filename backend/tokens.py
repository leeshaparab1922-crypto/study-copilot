"""Backend-issued signed opaque tokens asserting a student_id.

Plain deterministic module — no LLM/Crew calls, no network I/O, no database.
This is issuance-and-verification only; nothing in this module enforces
anything on an HTTP route (see backend/auth.py, a later step, for that).

Token format: two base64url segments joined by ".":

    base64url(json.dumps({"student_id": ..., "iat": <unix ts>})) + "." + base64url(hmac_sha256(payload_bytes))

The HMAC is computed over the RAW PAYLOAD BYTES (the bytes that were
base64url-encoded into the first segment, not the encoded text itself), so
verification re-derives the same digest from the decoded payload bytes and
compares it against the decoded signature bytes using hmac.compare_digest
(constant-time — this resists timing attacks; using `==` here would be a
real vulnerability, not a style nit).

Signing secret: STUDENT_TOKEN_SECRET env var, read once at import time. If
unset, a random 32-byte secret is generated once at module load (not
per-call — regenerating per call would make every previously issued token
fail verification within the same process) and a warning is logged that
tokens will only be valid for this process's lifetime (a restart mints a
new random secret, invalidating all previously issued tokens).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)


def _load_secret() -> bytes:
    env_secret = os.environ.get("STUDENT_TOKEN_SECRET")
    if env_secret:
        return env_secret.encode("utf-8")
    logger.warning(
        "STUDENT_TOKEN_SECRET is not set — generating a random signing secret "
        "for this process only. Tokens issued now will fail verification "
        "after any backend restart. Set STUDENT_TOKEN_SECRET in .env for "
        "tokens to survive a restart."
    )
    return secrets.token_bytes(32)


_SECRET = _load_secret()


class InvalidTokenError(Exception):
    """Raised by verify_token for any malformed, tampered, or semantically
    invalid token (bad base64, signature mismatch, missing/empty
    student_id, non-JSON payload, wrong number of segments)."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload_bytes: bytes) -> bytes:
    return hmac.new(_SECRET, payload_bytes, hashlib.sha256).digest()


def issue_token(student_id: str) -> str:
    """Mint a signed token asserting student_id. No credential check —
    matches this app's current no-account model (see backend/routes.py's
    POST /auth/token docstring)."""
    payload = {"student_id": student_id, "iat": int(time.time())}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = _sign(payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def verify_token(token: str) -> str:
    """Verify a token's signature and return its embedded student_id.

    Raises InvalidTokenError for any malformed token, signature mismatch,
    non-JSON/missing-student_id payload, or empty-string student_id."""
    if not isinstance(token, str) or token.count(".") != 1:
        raise InvalidTokenError("Malformed token: expected exactly one '.' separator.")

    payload_segment, signature_segment = token.split(".")

    try:
        payload_bytes = _b64url_decode(payload_segment)
        signature_bytes = _b64url_decode(signature_segment)
    except Exception as exc:  # binascii.Error and friends
        raise InvalidTokenError("Malformed token: invalid base64 encoding.") from exc

    expected_signature = _sign(payload_bytes)
    if not hmac.compare_digest(signature_bytes, expected_signature):
        raise InvalidTokenError("Token signature does not match.")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTokenError("Malformed token: payload is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise InvalidTokenError("Malformed token: payload is not a JSON object.")

    student_id = payload.get("student_id")
    if not isinstance(student_id, str) or student_id == "":
        raise InvalidTokenError("Malformed token: missing or empty student_id.")

    return student_id
