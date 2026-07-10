"""Pure-function tests for backend/tokens.py's HMAC-signed token
issuance/verification. No TestClient, no LLM/Crew calls, no I/O beyond the
in-process HMAC math."""

import base64
import json

import pytest

from backend.tokens import InvalidTokenError, issue_token, verify_token


def _b64url_decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def test_issue_then_verify_round_trips_to_same_student_id():
    token = issue_token("student-123")
    assert verify_token(token) == "student-123"


def test_tampering_with_payload_segment_raises_invalid_token_error():
    token = issue_token("student-123")
    payload_segment, signature_segment = token.split(".")

    payload = json.loads(_b64url_decode(payload_segment))
    payload["student_id"] = "someone-else"
    tampered_payload_segment = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    tampered_token = f"{tampered_payload_segment}.{signature_segment}"

    with pytest.raises(InvalidTokenError):
        verify_token(tampered_token)


def test_tampering_with_signature_segment_raises_invalid_token_error():
    token = issue_token("student-123")
    payload_segment, signature_segment = token.split(".")

    signature_bytes = bytearray(_b64url_decode(signature_segment))
    signature_bytes[0] ^= 0xFF  # flip a byte
    tampered_signature_segment = _b64url_encode(bytes(signature_bytes))
    tampered_token = f"{payload_segment}.{tampered_signature_segment}"

    with pytest.raises(InvalidTokenError):
        verify_token(tampered_token)


def test_malformed_token_with_no_separator_raises_invalid_token_error():
    with pytest.raises(InvalidTokenError):
        verify_token("not-a-valid-token-at-all")


def test_validly_signed_token_with_empty_student_id_raises_invalid_token_error():
    payload = {"student_id": "", "iat": 1234567890}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    import hashlib
    import hmac

    from backend import tokens as tokens_module

    signature = hmac.new(tokens_module._SECRET, payload_bytes, hashlib.sha256).digest()
    token = f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"

    with pytest.raises(InvalidTokenError):
        verify_token(token)


def test_two_tokens_for_same_student_at_different_times_both_verify_independently(monkeypatch):
    import backend.tokens as tokens_module

    monkeypatch.setattr(tokens_module.time, "time", lambda: 1_000_000)
    token_a = issue_token("student-123")

    monkeypatch.setattr(tokens_module.time, "time", lambda: 2_000_000)
    token_b = issue_token("student-123")

    assert token_a != token_b
    assert verify_token(token_a) == "student-123"
    assert verify_token(token_b) == "student-123"
