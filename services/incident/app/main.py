from __future__ import annotations
import secrets
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from shared.config import INTERNAL_API_TOKEN
from shared.database import get_db, init_db
from shared.event_schemas import AlertPayload
from shared.models import Incident, TimelineEvent, RoutingKey
from app.lifecycle import dispatch_alert

app = FastAPI(title="OpsPulse Incidents", version="1.0.0")

@app.on_event("startup")
def startup():
    init_db()

class InternalIngest(BaseModel):
    routing_key_id: int = Field(gt=0)
    payload: dict

class IncidentAction(BaseModel):
    state_message: str = Field(default="", max_length=10000)

@app.get("/health")
def health():
    return {"status": "ok", "service": "incident"}

@app.post("/internal/ingest")
def internal_ingest(
    body: InternalIngest,
    x_internal_service_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not x_internal_service_token or not secrets.compare_digest(x_internal_service_token, INTERNAL_API_TOKEN):
        raise HTTPException(status_code=401, detail={"result": "failure", "message": "Internal service authentication failed"})
    try:
        payload = AlertPayload.model_validate(body.payload).model_dump(exclude_none=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"result": "failure", "message": "Invalid alert payload"}) from exc
    key = db.scalar(select(RoutingKey).where(RoutingKey.id == body.routing_key_id, RoutingKey.enabled.is_(True)))
    if not key:
        raise HTTPException(status_code=401, detail={"result": "failure", "message": "Routing key is disabled or unavailable"})
    return dispatch_alert(db, key, payload)

@app.get("/")
def list_incidents(limit: int = 100, status: str | None = None, x_opspulse_organization_id: int | None = Header(default=None), db: Session = Depends(get_db)):
    if not x_opspulse_organization_id:
        raise HTTPException(401, "Organization context is missing")
    limit = max(1, min(limit, 1000))
    query = select(Incident).where(Incident.organization_id == x_opspulse_organization_id).order_by(desc(Incident.created_at)).limit(limit)
    if status:
        if status not in {"open", "acknowledged", "resolved"}:
            raise HTTPException(400, "Invalid incident status")
        query = select(Incident).where(Incident.organization_id == x_opspulse_organization_id, Incident.status == status).order_by(desc(Incident.created_at)).limit(limit)
    rows = db.scalars(query).all()
    return [{
        "id": row.id, "incident_id": row.incident_key, "entity_id": row.entity_id,
        "entity_display_name": row.entity_display_name, "state_message": row.state_message,
        "message_type": row.message_type, "status": row.status, "team_id": row.team_id,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    } for row in rows]

@app.post("/{incident_key}/acknowledge")
def acknowledge_incident(incident_key: str, body: IncidentAction, x_opspulse_organization_id: int | None = Header(default=None), x_opspulse_user_email: str | None = Header(default=None), db: Session = Depends(get_db)):
    row = db.scalar(select(Incident).where(Incident.incident_key == incident_key, Incident.organization_id == x_opspulse_organization_id))
    if not row:
        raise HTTPException(404, "Incident not found")
    if row.status == "resolved":
        raise HTTPException(409, "Resolved incidents cannot be acknowledged")
    key = db.get(RoutingKey, row.routing_key_id)
    if not key or not key.enabled:
        raise HTTPException(409, "The incident routing key is disabled")
    return dispatch_alert(db, key, {"message_type": "ACKNOWLEDGEMENT", "entity_id": row.entity_id, "state_message": body.state_message}, actor=x_opspulse_user_email or "user")

@app.post("/{incident_key}/resolve")
def resolve_incident(incident_key: str, body: IncidentAction, x_opspulse_organization_id: int | None = Header(default=None), x_opspulse_user_email: str | None = Header(default=None), db: Session = Depends(get_db)):
    row = db.scalar(select(Incident).where(Incident.incident_key == incident_key, Incident.organization_id == x_opspulse_organization_id))
    if not row:
        raise HTTPException(404, "Incident not found")
    if row.status == "resolved":
        return {"entity_id": row.entity_id, "incident_id": row.incident_key, "message": "Incident already resolved"}
    key = db.get(RoutingKey, row.routing_key_id)
    if not key or not key.enabled:
        raise HTTPException(409, "The incident routing key is disabled")
    return dispatch_alert(db, key, {"message_type": "RECOVERY", "entity_id": row.entity_id, "state_message": body.state_message}, actor=x_opspulse_user_email or "user")

@app.get("/{incident_key}")
def get_incident(incident_key: str, x_opspulse_organization_id: int | None = Header(default=None), db: Session = Depends(get_db)):
    row = db.scalar(select(Incident).where(Incident.incident_key == incident_key, Incident.organization_id == x_opspulse_organization_id))
    if not row:
        raise HTTPException(404, "Incident not found")
    events = db.scalars(select(TimelineEvent).where(TimelineEvent.incident_id == row.id).order_by(TimelineEvent.created_at, TimelineEvent.id)).all()
    return {
        "incident_id": row.incident_key, "entity_id": row.entity_id,
        "entity_display_name": row.entity_display_name, "state_message": row.state_message,
        "message_type": row.message_type, "status": row.status, "team_id": row.team_id,
        "annotations": row.annotations, "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "timeline": [{"type": event.event_type, "actor": event.actor, "message": event.message, "details": event.details, "created_at": event.created_at.isoformat()} for event in events],
    }
