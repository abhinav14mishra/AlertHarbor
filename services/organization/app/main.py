from __future__ import annotations
import secrets
import hashlib
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from shared.database import get_db, init_db
from shared.models import Organization, Team, RoutingKey, AuditEvent

app = FastAPI(title="OpsPulse Organization", version="1.0.0")

@app.on_event("startup")
def startup():
    init_db()

class TeamInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)

class KeyInput(BaseModel):
    team_id: int = Field(gt=0)
    name: str = Field(default="Default integration", min_length=1, max_length=120)
    warnings_enabled: bool = True


def _org_id(value: int | None) -> int:
    if not value or value < 1:
        raise HTTPException(401, "Organization context is missing")
    return value

@app.get("/health")
def health():
    return {"status": "ok", "service": "organization"}

@app.get("/workspace")
def workspace(x_opspulse_organization_id: int | None = Header(default=None), db: Session = Depends(get_db)):
    organization = db.get(Organization, _org_id(x_opspulse_organization_id))
    if not organization:
        raise HTTPException(404, "Workspace not found")
    return {"id": organization.id, "name": organization.name, "created_at": organization.created_at.isoformat()}

@app.get("/teams")
def list_teams(x_opspulse_organization_id: int | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _org_id(x_opspulse_organization_id)
    return [{"id": row.id, "name": row.name, "description": row.description} for row in db.scalars(
        select(Team).where(Team.organization_id == org_id).order_by(Team.name, Team.id)
    ).all()]

@app.post("/teams", status_code=201)
def create_team(body: TeamInput, x_opspulse_organization_id: int | None = Header(default=None), x_opspulse_user_email: str | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _org_id(x_opspulse_organization_id)
    if not db.get(Organization, org_id):
        raise HTTPException(400, "Invalid organization context")
    if db.scalar(select(Team.id).where(Team.organization_id == org_id, Team.name == body.name)):
        raise HTTPException(409, "Team name already exists in this workspace")
    row = Team(name=body.name.strip(), organization_id=org_id, description=body.description.strip())
    db.add(row); db.flush()
    db.add(AuditEvent(actor=x_opspulse_user_email or "system", action="team.created", resource_type="team", resource_id=str(row.id), organization_id=org_id, details={"name": row.name, "organization_id": org_id}))
    db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "description": row.description}

@app.get("/routing-keys")
def list_keys(x_opspulse_organization_id: int | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _org_id(x_opspulse_organization_id)
    rows = db.execute(select(RoutingKey, Team).join(Team, RoutingKey.team_id == Team.id).where(Team.organization_id == org_id).order_by(desc(RoutingKey.created_at))).all()
    return [{"id": key.id, "name": key.name, "key_prefix": key.key_prefix, "team_id": key.team_id, "warnings_enabled": key.warnings_enabled, "enabled": key.enabled, "created_at": key.created_at.isoformat()} for key, team in rows]

@app.post("/routing-keys", status_code=201)
def create_key(body: KeyInput, x_opspulse_organization_id: int | None = Header(default=None), x_opspulse_user_email: str | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _org_id(x_opspulse_organization_id)
    team = db.scalar(select(Team).where(Team.id == body.team_id, Team.organization_id == org_id))
    if not team:
        raise HTTPException(404, "Team not found in this workspace")
    raw_key = "opsp_" + secrets.token_urlsafe(32)
    row = RoutingKey(key_hash=hashlib.sha256(raw_key.encode()).hexdigest(), key_prefix=raw_key[:12], team_id=team.id, name=body.name, warnings_enabled=body.warnings_enabled)
    db.add(row); db.flush()
    db.add(AuditEvent(actor=x_opspulse_user_email or "system", action="routing_key.created", resource_type="routing_key", resource_id=str(row.id), organization_id=org_id, details={"team_id": team.id, "organization_id": org_id}))
    db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "key": raw_key, "key_prefix": row.key_prefix, "team_id": row.team_id, "warnings_enabled": row.warnings_enabled, "enabled": row.enabled}

@app.post("/routing-keys/{key_id}/revoke")
def revoke_key(key_id: int, x_opspulse_organization_id: int | None = Header(default=None), x_opspulse_user_email: str | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _org_id(x_opspulse_organization_id)
    row = db.scalar(select(RoutingKey).join(Team, RoutingKey.team_id == Team.id).where(RoutingKey.id == key_id, Team.organization_id == org_id))
    if not row:
        raise HTTPException(404, "Routing key not found")
    row.enabled = False
    db.add(AuditEvent(actor=x_opspulse_user_email or "system", action="routing_key.revoked", resource_type="routing_key", resource_id=str(row.id), organization_id=org_id, details={"organization_id": org_id}))
    db.commit()
    return {"status": "revoked"}
