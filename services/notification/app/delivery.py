"""Synchronous notification delivery primitive for internal service callers."""
from __future__ import annotations
import re
from app.providers import send_email

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def dispatch_notification(event: dict) -> dict:
    recipients = event.get("recipients")
    subject = event.get("subject")
    body = event.get("body")
    if not isinstance(recipients, list) or not recipients:
        raise ValueError("recipients must be a non-empty list")
    if not isinstance(subject, str) or not subject.strip() or not isinstance(body, str) or not body.strip():
        raise ValueError("subject and body are required")
    results = []
    for raw in dict.fromkeys(recipients):
        if not isinstance(raw, str) or not _EMAIL.fullmatch(raw.strip()):
            results.append({"recipient": str(raw), "sent": False, "error": "invalid_recipient"})
            continue
        recipient = raw.strip().lower()
        try:
            send_email(recipient, subject[:200], body[:50000])
            results.append({"recipient": recipient, "sent": True})
        except Exception as exc:
            results.append({"recipient": recipient, "sent": False, "error": type(exc).__name__})
    return {"accepted": len(results), "sent": sum(1 for result in results if result["sent"]), "results": results}
