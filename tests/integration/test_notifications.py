from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).parents[2]
TASKS_PATH = ROOT / "services" / "worker" / "app" / "tasks.py"
SPEC = importlib.util.spec_from_file_location("opspulse_worker_tasks_test", TASKS_PATH)
TASKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TASKS)

from shared.database import Base
from shared.models import EscalationPolicy, EscalationTask, Incident, NotificationDelivery, OnCallSchedule, Organization, RoutingKey, Team


def test_triggered_event_notifies_current_on_call_only_once(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        organization = Organization(name="Notification Workspace")
        db.add(organization); db.flush()
        team = Team(name="SRE", organization_id=organization.id, description="SRE")
        db.add(team); db.flush()
        key = RoutingKey(key_hash=hashlib.sha256("notify-test-key".encode()).hexdigest(), key_prefix="notify-test", team_id=team.id)
        db.add(key); db.flush()
        incident = Incident(
            incident_key="incident-notify-test", entity_id="checkout", entity_display_name="Checkout",
            state_message="HTTP 500", message_type="CRITICAL", status="open", team_id=team.id,
            organization_id=organization.id, routing_key_id=key.id, payload={}, annotations={},
        )
        db.add(incident)
        db.add(OnCallSchedule(team_id=team.id, name="Primary", members=["oncall@example.com"], rotation_hours=168, enabled=True))
        db.commit()
        team_id = team.id

    sent = []
    monkeypatch.setattr(TASKS, "SessionLocal", Session)
    monkeypatch.setattr(TASKS, "_send_email", lambda recipient, subject, body: sent.append((recipient, subject)))
    event = {"event_id": "event-123", "event": "incident.triggered", "team_id": team_id, "result": {"incident_id": "incident-notify-test"}}
    assert TASKS.handle_event(event) is True
    assert TASKS.handle_event(event) is True
    assert len(sent) == 1
    assert sent[0][0] == "oncall@example.com"
    with Session() as db:
        delivery = db.scalar(select(NotificationDelivery))
        assert delivery.status == "sent"
        assert delivery.attempts == 1
        assert db.scalar(select(func.count(NotificationDelivery.id))) == 1
    engine.dispose()


def test_delayed_escalation_is_scheduled_and_delivered_once(monkeypatch):
    from datetime import datetime, timedelta, timezone
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        organization = Organization(name="Escalation Workspace")
        db.add(organization); db.flush()
        team = Team(name="API", organization_id=organization.id, description="API")
        db.add(team); db.flush()
        key = RoutingKey(key_hash=hashlib.sha256("escalation-test-key".encode()).hexdigest(), key_prefix="escalation", team_id=team.id)
        db.add(key); db.flush()
        db.add(Incident(incident_key="incident-escalation-test", entity_id="api", entity_display_name="API", state_message="timeout", message_type="CRITICAL", status="open", organization_id=organization.id, team_id=team.id, routing_key_id=key.id, payload={}, annotations={}))
        db.add(OnCallSchedule(team_id=team.id, name="Primary", members=["primary@example.com"], rotation_hours=168, enabled=True))
        db.add(EscalationPolicy(team_id=team.id, name="Escalate", rules=[{"delay_minutes": 5, "recipients": ["lead@example.com"]}], enabled=True))
        db.commit(); team_id = team.id
    sent = []
    monkeypatch.setattr(TASKS, "SessionLocal", Session)
    monkeypatch.setattr(TASKS, "_send_email", lambda recipient, subject, body: sent.append(recipient))
    event = {"event_id": "event-escalation-1", "event": "incident.triggered", "team_id": team_id, "result": {"incident_id": "incident-escalation-test"}}
    TASKS.handle_event(event)
    TASKS.handle_event(event)
    with Session() as db:
        task = db.scalar(select(EscalationTask))
        assert task is not None and task.status == "pending"
        task.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert TASKS.dispatch_due_escalations_once() == 1
    assert sent.count("primary@example.com") == 1
    assert sent.count("lead@example.com") == 1
    with Session() as db:
        task = db.scalar(select(EscalationTask))
        assert task.status == "completed"
    engine.dispose()
