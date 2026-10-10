from __future__ import annotations
import logging
import os
import re
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from shared.database import SessionLocal
from shared.models import EscalationPolicy, EscalationTask, Incident, NotificationDelivery, OnCallSchedule

logger = logging.getLogger("opspulse.worker")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _current_on_call(schedule: OnCallSchedule, at: datetime | None = None) -> str | None:
    members = schedule.members or []
    if not members or not schedule.enabled:
        return None
    at = at or datetime.now(timezone.utc)
    hours = max(1, int(schedule.rotation_hours or 168))
    slot = int(at.timestamp() // (hours * 3600))
    member = members[slot % len(members)]
    return member.strip().lower() if isinstance(member, str) else None


def _send_email(recipient: str, subject: str, body: str) -> None:
    base_url = os.getenv("NOTIFICATION_URL", "http://notification:8000").rstrip("/")
    response = httpx.post(
        f"{base_url}/email",
        json={"to": recipient, "subject": subject, "body": body},
        timeout=httpx.Timeout(12.0, connect=3.0),
    )
    response.raise_for_status()
    if response.json().get("sent") is not True:
        raise RuntimeError("Notification service did not confirm email delivery")


def _deliver_once(db, event_key: str, recipient: str, subject: str, body: str) -> None:
    delivery = db.scalar(select(NotificationDelivery).where(
        NotificationDelivery.event_key == event_key,
        NotificationDelivery.recipient == recipient,
    ))
    if delivery and delivery.status == "sent":
        return
    if not delivery:
        delivery = NotificationDelivery(event_key=event_key, recipient=recipient, status="pending")
        db.add(delivery)
        db.flush()
    delivery.attempts += 1
    db.commit()
    try:
        _send_email(recipient, subject, body)
    except Exception as exc:
        delivery.status = "failed"
        delivery.last_error = type(exc).__name__
        db.commit()
        raise
    delivery.status = "sent"
    delivery.last_error = ""
    delivery.sent_at = datetime.now(timezone.utc)
    db.commit()


def _schedule_escalations(db, event_key: str, team_id: int, incident_key: str) -> None:
    policy = db.scalar(select(EscalationPolicy).where(EscalationPolicy.team_id == team_id, EscalationPolicy.enabled.is_(True)))
    if not policy:
        return
    now = datetime.now(timezone.utc)
    for index, rule in enumerate(policy.rules or []):
        if not isinstance(rule, dict):
            continue
        try:
            delay_minutes = int(rule.get("delay_minutes", 0))
            recipients = list(dict.fromkeys(
                recipient.strip().lower() for recipient in (rule.get("recipients") or [])
                if isinstance(recipient, str) and _EMAIL.fullmatch(recipient.strip())
            ))
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid escalation rule index=%s team_id=%s", index, team_id)
            continue
        if delay_minutes < 0 or delay_minutes > 10080 or not recipients:
            continue
        existing = db.scalar(select(EscalationTask.id).where(
            EscalationTask.source_event_key == event_key,
            EscalationTask.rule_index == index,
        ))
        if existing:
            continue
        db.add(EscalationTask(
            source_event_key=event_key,
            rule_index=index,
            team_id=team_id,
            incident_key=incident_key,
            recipients=recipients,
            due_at=now + timedelta(minutes=delay_minutes),
            status="pending",
        ))
    db.commit()


def handle_event(event: dict):
    """Handle lifecycle events and schedule durable, idempotent notifications."""
    event_name = event.get("event", "unknown")
    if event_name != "incident.triggered":
        logger.info("Processed lifecycle event %s", event_name)
        return True
    event_key = event.get("event_id")
    team_id = event.get("team_id")
    incident_key = (event.get("result") or {}).get("incident_id")
    if not event_key or not isinstance(team_id, int) or not incident_key:
        raise ValueError("Triggered incident event is missing event_id, team_id, or incident_id")

    with SessionLocal() as db:
        incident = db.scalar(select(Incident).where(Incident.incident_key == incident_key))
        schedule = db.scalar(select(OnCallSchedule).where(OnCallSchedule.team_id == team_id, OnCallSchedule.enabled.is_(True)))
        recipient = _current_on_call(schedule) if schedule else None
        _schedule_escalations(db, event_key, team_id, incident_key)
        if recipient and _EMAIL.fullmatch(recipient):
            title = incident.entity_display_name if incident else incident_key
            state = incident.state_message if incident else "An incident was triggered."
            subject = f"[OpsPulse] Incident triggered: {title}"
            body = (
                f"An incident has been triggered in OpsPulse.\n\n"
                f"Incident: {incident_key}\nEntity: {title}\nEntity ID: {incident.entity_id if incident else 'unknown'}\n"
                f"Team ID: {team_id}\nStatus: {incident.status if incident else 'unknown'}\n\n"
                f"Message: {state}\n\nReview the incident in your OpsPulse workspace."
            )
            _deliver_once(db, event_key, recipient, subject, body)
        else:
            logger.warning("No valid on-call email is configured for team_id=%s", team_id)
    return True


def dispatch_due_escalations_once(batch_size: int = 25) -> int:
    sent = 0
    now = datetime.now(timezone.utc)
    for _ in range(max(1, min(batch_size, 100))):
        with SessionLocal() as db:
            try:
                task = db.scalar(select(EscalationTask).where(
                    EscalationTask.status.in_(["pending", "processing"]),
                    EscalationTask.due_at <= now,
                ).order_by(EscalationTask.due_at, EscalationTask.id).with_for_update(skip_locked=True).limit(1))
                if task is None:
                    db.rollback()
                    break
                task.status = "processing"
                task.attempts += 1
                task.due_at = datetime.now(timezone.utc) + timedelta(seconds=60)
                db.commit()  # Lease the task; another worker cannot claim it until the lease expires.
                incident = db.scalar(select(Incident).where(Incident.incident_key == task.incident_key))
                if not incident or incident.status in {"acknowledged", "resolved"}:
                    task.status = "cancelled"
                    task.completed_at = datetime.now(timezone.utc)
                    db.commit()
                    continue
                subject = f"[OpsPulse] Escalation: {incident.entity_display_name or incident.entity_id}"
                body = (
                    f"An incident remains unacknowledged and has reached an escalation step.\n\n"
                    f"Incident: {incident.incident_key}\nEntity: {incident.entity_display_name or incident.entity_id}\n"
                    f"Status: {incident.status}\nMessage: {incident.state_message}\n"
                )
                try:
                    for recipient in task.recipients or []:
                        if isinstance(recipient, str) and _EMAIL.fullmatch(recipient):
                            _deliver_once(db, task.task_key, recipient, subject, body)
                    task.status = "completed"
                    task.completed_at = datetime.now(timezone.utc)
                    task.last_error = ""
                    db.commit()
                    sent += 1
                except Exception as exc:
                    task.status = "pending"
                    task.last_error = type(exc).__name__
                    task.due_at = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** min(task.attempts, 8)))
                    db.commit()
                    logger.exception("Escalation delivery failed; retry scheduled")
            except Exception:
                db.rollback()
                logger.exception("Escalation scheduler failed")
                break
    return sent
