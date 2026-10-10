from __future__ import annotations
import hashlib
import sys
from pathlib import Path
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).parents[2]
INCIDENT_SERVICE = ROOT / "services" / "incident"
if str(INCIDENT_SERVICE) not in sys.path:
    sys.path.insert(0, str(INCIDENT_SERVICE))

from shared.database import Base
from shared.models import AuditEvent, Incident, Organization, OutboxEvent, RoutingKey, Team, TimelineEvent
from app.lifecycle import dispatch_alert


def database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    organization = Organization(name="Test Workspace")
    session.add(organization); session.flush()
    team = Team(name="Platform", organization_id=organization.id, description="Platform services")
    session.add(team)
    session.flush()
    key = RoutingKey(key_hash=hashlib.sha256("test-routing-key".encode()).hexdigest(), key_prefix="test-rout", team_id=team.id, warnings_enabled=True, enabled=True)
    session.add(key)
    session.commit()
    return engine, session, team, key


def test_trigger_ack_info_recovery_lifecycle_is_persisted():
    engine, db, team, key = database()
    try:
        first = dispatch_alert(db, key, {"message_type": "CRITICAL", "entity_id": "checkout", "state_message": "HTTP 500"})
        assert first["entity_id"] == "checkout"
        incident = db.scalar(select(Incident).where(Incident.entity_id == "checkout"))
        assert incident.status == "open"
        assert db.scalar(select(func.count(OutboxEvent.id))) == 1

        ack = dispatch_alert(db, key, {"message_type": "ACKNOWLEDGEMENT", "entity_id": "checkout", "state_message": "Investigating"})
        assert ack["incident_id"] == incident.incident_key
        db.refresh(incident)
        assert incident.status == "acknowledged"
        assert incident.acknowledged_at is not None

        dispatch_alert(db, key, {"message_type": "INFO", "entity_id": "checkout", "state_message": "Runbook checked", "vo_annotate.s.Note": "Restart worker"})
        db.refresh(incident)
        assert incident.annotations["vo_annotate.s.Note"] == "Restart worker"

        dispatch_alert(db, key, {"message_type": "RECOVERY", "entity_id": "checkout", "state_message": "Service recovered"})
        db.refresh(incident)
        assert incident.status == "resolved"
        assert db.scalar(select(func.count(TimelineEvent.id)).where(TimelineEvent.incident_id == incident.id)) == 4
        assert db.scalar(select(func.count(AuditEvent.id))) == 4
        assert db.scalar(select(func.count(OutboxEvent.id))) == 4
    finally:
        db.close(); engine.dispose()


def test_critical_after_recovery_opens_a_new_incident():
    engine, db, team, key = database()
    try:
        first = dispatch_alert(db, key, {"message_type": "CRITICAL", "entity_id": "database", "state_message": "down"})
        dispatch_alert(db, key, {"message_type": "RECOVERY", "entity_id": "database"})
        second = dispatch_alert(db, key, {"message_type": "CRITICAL", "entity_id": "database", "state_message": "down again"})
        assert first["incident_id"] != second["incident_id"]
        assert db.scalar(select(func.count(Incident.id))) == 2
    finally:
        db.close(); engine.dispose()


def test_warning_disabled_does_not_create_incident_or_outbox_event():
    engine, db, team, key = database()
    try:
        key.warnings_enabled = False
        db.commit()
        result = dispatch_alert(db, key, {"message_type": "WARNING", "entity_id": "cpu", "state_message": "high"})
        assert "ignored" in result["message"]
        assert db.scalar(select(func.count(Incident.id))) == 0
        assert db.scalar(select(func.count(OutboxEvent.id))) == 0
    finally:
        db.close(); engine.dispose()


def test_same_entity_in_different_teams_does_not_aggregate_across_teams():
    engine, db, team, key = database()
    try:
        other = Team(name="Payments", organization_id=team.organization_id, description="Payments")
        db.add(other); db.flush()
        other_key = RoutingKey(key_hash=hashlib.sha256("other-key".encode()).hexdigest(), key_prefix="other-key", team_id=other.id, warnings_enabled=True, enabled=True)
        db.add(other_key); db.commit()
        first = dispatch_alert(db, key, {"message_type": "CRITICAL", "entity_id": "shared-id"})
        second = dispatch_alert(db, other_key, {"message_type": "CRITICAL", "entity_id": "shared-id"})
        assert first["incident_id"] != second["incident_id"]
        assert db.scalar(select(func.count(Incident.id))) == 2
    finally:
        db.close(); engine.dispose()


def test_retention_keeps_only_latest_incidents_per_organization(monkeypatch):
    import app.lifecycle as lifecycle
    engine, db, team, key = database()
    try:
        monkeypatch.setattr(lifecycle, "INCIDENT_RETENTION_LIMIT", 2)
        other_org = Organization(name="Other Workspace")
        db.add(other_org); db.flush()
        other_team = Team(name="Platform", organization_id=other_org.id, description="Other tenant")
        db.add(other_team); db.flush()
        other_key = RoutingKey(key_hash=hashlib.sha256("other-workspace-key".encode()).hexdigest(), key_prefix="other-work", team_id=other_team.id)
        db.add(other_key); db.commit()
        for entity in ("one", "two", "three"):
            dispatch_alert(db, key, {"message_type": "CRITICAL", "entity_id": entity})
            dispatch_alert(db, other_key, {"message_type": "CRITICAL", "entity_id": entity})
        incidents = db.scalars(select(Incident).order_by(Incident.id)).all()
        assert len(incidents) == 4
        assert {row.entity_id for row in incidents if row.organization_id == team.organization_id} == {"two", "three"}
        assert {row.entity_id for row in incidents if row.organization_id == other_org.id} == {"two", "three"}
        assert db.scalar(select(func.count(TimelineEvent.id))) == 4
    finally:
        db.close(); engine.dispose()


def test_routing_key_lookup_uses_hash_and_rejects_revoked_keys():
    import importlib.util
    from fastapi import HTTPException
    spec = importlib.util.spec_from_file_location("opspulse_routing_module", ROOT / "services" / "alert-routing" / "app" / "routing.py")
    routing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routing)
    engine, db, team, key = database()
    try:
        assert routing.resolve_routing_key(db, "test-routing-key").id == key.id
        key.enabled = False
        db.commit()
        try:
            routing.resolve_routing_key(db, "test-routing-key")
            assert False, "disabled key should not resolve"
        except HTTPException as exc:
            assert exc.status_code == 401
    finally:
        db.close(); engine.dispose()
