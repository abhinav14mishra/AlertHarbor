"""Environment configuration with fail-closed production validation."""
from __future__ import annotations

import os

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://opspulse:opspulse@localhost:5432/opspulse",
)
JWT_SECRET = os.getenv("JWT_SECRET", "local-only-change-this-jwt-secret-before-deploying")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
ALLOW_SELF_REGISTRATION = os.getenv("ALLOW_SELF_REGISTRATION", "true" if APP_ENV != "production" else "false").lower() == "true"
AUTO_CREATE_SCHEMA = os.getenv("AUTO_CREATE_SCHEMA", "true" if APP_ENV != "production" else "false").lower() == "true"
MAX_ALERT_BODY_BYTES = int(os.getenv("MAX_ALERT_BODY_BYTES", "1048576"))
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "local-only-internal-token-change-before-production")
INCIDENT_RETENTION_LIMIT = int(os.getenv("INCIDENT_RETENTION_LIMIT", "1000"))
SMTP_HOST = os.getenv("SMTP_HOST", "mailpit")
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "opspulse@localhost")
SMTP_TLS = os.getenv("SMTP_TLS", "false").lower() == "true"


def _placeholder(value: str) -> bool:
    normalized = value.lower()
    return any(marker in normalized for marker in ("replace-with", "change-this", "changeme", "your-secret", "local-only", "example"))


if APP_ENV == "production":
    if len(JWT_SECRET) < 32 or _placeholder(JWT_SECRET):
        raise RuntimeError("JWT_SECRET must be a unique secret of at least 32 characters in production")
    if DATABASE_URL.startswith("sqlite:") or "opspulse-local-db-password" in DATABASE_URL or "opspulse:opspulse@" in DATABASE_URL:
        raise RuntimeError("DATABASE_URL contains a development-only database configuration")
    if len(INTERNAL_API_TOKEN) < 32 or _placeholder(INTERNAL_API_TOKEN):
        raise RuntimeError("INTERNAL_API_TOKEN must be a unique secret of at least 32 characters in production")
    if _placeholder(DATABASE_URL) or _placeholder(RABBITMQ_URL) or "opspulse-local-rabbit-password" in RABBITMQ_URL or "guest:guest@" in RABBITMQ_URL:
        raise RuntimeError("RABBITMQ_URL contains development credentials")
    if SMTP_HOST.lower() == "mailpit" or not SMTP_USERNAME or not SMTP_PASSWORD or _placeholder(SMTP_PASSWORD) or _placeholder(SMTP_HOST) or not SMTP_TLS or SMTP_FROM.lower().endswith("@localhost") or "@" not in SMTP_FROM:
        raise RuntimeError("Production email delivery requires a real SMTP host, credentials, and STARTTLS")
    if ALLOW_SELF_REGISTRATION:
        raise RuntimeError("ALLOW_SELF_REGISTRATION must be false in production")
    if AUTO_CREATE_SCHEMA:
        raise RuntimeError("AUTO_CREATE_SCHEMA must be false in production; apply migrations before startup")
    if INCIDENT_RETENTION_LIMIT < 100:
        raise RuntimeError("INCIDENT_RETENTION_LIMIT must be at least 100")
    if MAX_ALERT_BODY_BYTES < 4096:
        raise RuntimeError("MAX_ALERT_BODY_BYTES must be at least 4096")
