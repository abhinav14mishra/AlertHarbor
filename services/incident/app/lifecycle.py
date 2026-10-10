from __future__ import annotations

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import desc, select, text, delete
from sqlalchemy.orm import Session
from shared.models import AuditEvent, EscalationTask, Incident, OutboxEvent, RoutingKey, Team, TimelineEvent
from shared.config import INCIDENT_RETENTION_LIMIT

ACTIVE_STATUSES = ("open", "acknowledged")

def extract_annotations(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key.startswith(("vo_annotate.u.", "vo_annotate.s.", "vo_annotate.i."))}

def _lock_entity(db: Session, team_id: int, entity_id: str) -> None:
    """Serialize lifecycle operations for a team/entity pair on PostgreSQL."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"opspulse:{team_id}:{entity_id}"},
        )


def _commit_with_outbox(db: Session, key, payload: dict, result: dict, event_name: str) -> dict:
    db.add(OutboxEvent(
        topic="incident.lifecycle",
        payload={
            "event": event_name,
            "routing_key_id": key.id,
            "team_id": key.team_id,
            "organization_id": result.get("organization_id"),
            "payload": payload,
            "result": result,
        },
    ))
    db.commit()
    return result


def _enforce_retention(db: Session, organization_id: int) -> None:
    """Retain the newest configured number of incidents for each workspace."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"), {"lock_key": f"opspulse:retention:{organization_id}"})
    older_ids = select(Incident.id).where(Incident.organization_id == organization_id).order_by(
        desc(Incident.created_at), desc(Incident.id)
    ).offset(INCIDENT_RETENTION_LIMIT)
    ids = list(db.scalars(older_ids).all())
    if ids:
        db.execute(delete(TimelineEvent).where(TimelineEvent.incident_id.in_(ids)))
        db.execute(delete(Incident).where(Incident.id.in_(ids)))


def dispatch_alert(db: Session, key, payload: dict, actor: str = "rest-endpoint") -> dict:
    typ = payload["message_type"]
    entity = payload["entity_id"]
    message = payload.get("state_message", "")
    display = payload.get("entity_display_name") or entity
    annotations = extract_annotations(payload)
    team = db.get(Team, key.team_id)
    if not team:
        raise HTTPException(status_code=409, detail={"result": "failure", "message": "Routing key team no longer exists"})
    organization_id = team.organization_id
    _lock_entity(db, key.team_id, entity)
    active = db.scalar(
        select(Incident)
        .where(
            Incident.team_id == key.team_id,
            Incident.entity_id == entity,
            Incident.status.in_(ACTIVE_STATUSES),
        )
        .order_by(desc(Incident.id))
        .with_for_update()
    )

    def record(row: Incident | None, event: str) -> None:
        db.add(TimelineEvent(
            incident_id=row.id if row else None,
            entity_id=entity,
            event_type=event,
            actor=actor,
            message=message,
            details={"message_type": typ, "annotations": annotations},
        ))
        db.add(AuditEvent(
            organization_id=organization_id,
            actor=actor,
            action=f"incident.{event.lower()}",
            resource_type="incident",
            resource_id=str(row.id) if row else entity,
            details={"entity_id": entity, "message_type": typ, "routing_key_id": key.id, "team_id": key.team_id},
        ))

    if typ == "WARNING" and not key.warnings_enabled:
        return {"entity_id": entity, "message": "WARNING ignored by routing-key policy"}

    if typ in ("CRITICAL", "WARNING"):
        if active:
            active.state_message = message or active.state_message
            active.entity_display_name = display
            active.message_type = typ
            active.payload = payload
            active.annotations = {**(active.annotations or {}), **annotations}
            active.updated_at = datetime.now(timezone.utc)
            record(active, "UPDATED")
            return _commit_with_outbox(db, key, payload, {
                "entity_id": entity, "incident_id": active.incident_key, "message": "Incident updated", "organization_id": organization_id
            }, "incident.updated")

        row = Incident(
            organization_id=organization_id,
            entity_id=entity,
            entity_display_name=display,
            state_message=message,
            message_type=typ,
            status="open",
            team_id=key.team_id,
            routing_key_id=key.id,
            payload=payload,
            annotations=annotations,
        )
        db.add(row)
        db.flush()
        record(row, "TRIGGERED")
        _enforce_retention(db, organization_id)
        return _commit_with_outbox(db, key, payload, {
            "entity_id": entity, "incident_id": row.incident_key, "message": "Incident created", "organization_id": organization_id
        }, "incident.triggered")

    if typ in ("ACKNOWLEDGEMENT", "RECOVERY") and not active:
        raise HTTPException(status_code=404, detail={
            "result": "failure", "message": f"No active incident found for entity_id '{entity}'"
        })

    if typ == "ACKNOWLEDGEMENT":
        db.query(EscalationTask).filter(EscalationTask.incident_key == active.incident_key, EscalationTask.status == "pending").update({"status": "cancelled"}, synchronize_session=False)
        if active.status != "acknowledged":
            active.status = "acknowledged"
            active.acknowledged_at = datetime.now(timezone.utc)
        active.state_message = message or active.state_message
        record(active, "ACKNOWLEDGED")
        return _commit_with_outbox(db, key, payload, {
            "entity_id": entity, "incident_id": active.incident_key, "message": "Incident acknowledged", "organization_id": organization_id
        }, "incident.acknowledged")

    if typ == "RECOVERY":
        db.query(EscalationTask).filter(EscalationTask.incident_key == active.incident_key, EscalationTask.status == "pending").update({"status": "cancelled"}, synchronize_session=False)
        active.status = "resolved"
        active.resolved_at = datetime.now(timezone.utc)
        active.state_message = message or active.state_message
        record(active, "RESOLVED")
        return _commit_with_outbox(db, key, payload, {
            "entity_id": entity, "incident_id": active.incident_key, "message": "Incident resolved", "organization_id": organization_id
        }, "incident.resolved")

    if typ == "INFO":
        if active and annotations:
            active.annotations = {**(active.annotations or {}), **annotations}
            active.updated_at = datetime.now(timezone.utc)
        record(active, "INFO")
        return _commit_with_outbox(db, key, payload, {
            "entity_id": entity,
            "incident_id": active.incident_key if active else None,
            "message": "Timeline event recorded", "organization_id": organization_id,
        }, "incident.info")

    raise HTTPException(status_code=422, detail={"result": "failure", "message": "Unsupported message_type"})

