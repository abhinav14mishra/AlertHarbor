"""Password hashing and minimal HS256 JWT support using the Python standard library."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from shared.config import JWT_SECRET

_ITERATIONS = 310_000
_ISSUER = "opspulse"


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(iterations)
        if rounds < 100_000 or rounds > 2_000_000:
            return False
        salt = _unb64(salt_text)
        expected = _unb64(digest_text)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(subject: str, role: str = "member", ttl: int = 3600, organization_id: int | None = None) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({
        "sub": subject,
        "role": role,
        "organization_id": organization_id,
        "iss": _ISSUER,
        "iat": now,
        "exp": now + max(60, min(int(ttl), 86_400)),
    }, separators=(",", ":")).encode())
    body = f"{header}.{payload}"
    signature = _b64(hmac.new(JWT_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def decode_token(token: str) -> dict:
    try:
        header_text, payload_text, signature = token.split(".", 2)
        header = json.loads(_unb64(header_text))
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError("Unsupported token header")
        body = f"{header_text}.{payload_text}"
        expected = _b64(hmac.new(JWT_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid token signature")
        payload = json.loads(_unb64(payload_text))
        now = int(time.time())
        if payload.get("iss") != _ISSUER or not isinstance(payload.get("sub"), str) or not payload["sub"]:
            raise ValueError("Invalid token claims")
        if not isinstance(payload.get("exp"), int) or payload["exp"] <= now:
            raise ValueError("Token expired")
        if not isinstance(payload.get("iat"), int) or payload["iat"] > now + 60:
            raise ValueError("Invalid token issue time")
        if payload.get("role") not in {"admin", "member"}:
            raise ValueError("Invalid token role")
        if not isinstance(payload.get("organization_id"), int) or payload["organization_id"] < 1:
            raise ValueError("Invalid token organization")
        return payload
    except Exception as exc:
        raise ValueError("Invalid or expired token") from exc
