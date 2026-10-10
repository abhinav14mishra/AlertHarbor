from __future__ import annotations
import re
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import select
from shared.database import get_db
from shared.models import Team, OnCallSchedule, EscalationPolicy, AuditEvent

router = APIRouter()
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

class ScheduleInput(BaseModel):
    team_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    members: list[str] = Field(min_length=1, max_length=100)
    rotation_hours: int = Field(default=168, ge=1, le=8760)
    enabled: bool = True

    @field_validator("members")
    @classmethod
    def validate_members(cls, members: list[str]) -> list[str]:
        normalized = [member.strip().lower() for member in members]
        if any(not _EMAIL.fullmatch(member) for member in normalized):
            raise ValueError("Every on-call member must be a valid email address")
        if len(set(normalized)) != len(normalized):
            raise ValueError("On-call members must be unique")
        return normalized

class EscalationRule(BaseModel):
    delay_minutes: int = Field(ge=0, le=10080)
    recipients: list[str] = Field(min_length=1, max_length=100)

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, recipients: list[str]) -> list[str]:
        normalized = [recipient.strip().lower() for recipient in recipients]
        if any(not _EMAIL.fullmatch(recipient) for recipient in normalized):
            raise ValueError("Every escalation recipient must be a valid email address")
        return list(dict.fromkeys(normalized))

class PolicyInput(BaseModel):
    team_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    rules: list[EscalationRule] = Field(default_factory=list, max_length=20)
    enabled: bool = True


def _organization_id(value: int | None) -> int:
    if not value:
        raise HTTPException(401, "Organization context is missing")
    return value

@router.get("/on-call")
def schedules(x_opspulse_organization_id: int | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _organization_id(x_opspulse_organization_id)
    rows = db.execute(select(OnCallSchedule, Team).join(Team, OnCallSchedule.team_id == Team.id).where(Team.organization_id == org_id)).all()
    return [{"id": row.id, "team_id": row.team_id, "name": row.name, "members": row.members, "rotation_hours": row.rotation_hours, "enabled": row.enabled} for row, team in rows]

@router.post("/on-call", status_code=201)
def create_schedule(body: ScheduleInput, x_opspulse_organization_id: int | None = Header(default=None), x_opspulse_user_email: str | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _organization_id(x_opspulse_organization_id)
    if not db.scalar(select(Team).where(Team.id == body.team_id, Team.organization_id == org_id)):
        raise HTTPException(404, "Team not found")
    row = db.scalar(select(OnCallSchedule).where(OnCallSchedule.team_id == body.team_id))
    values = body.model_dump()
    if row:
        row.name = values["name"]; row.members = values["members"]; row.rotation_hours = values["rotation_hours"]; row.enabled = values["enabled"]
    else:
        row = OnCallSchedule(**values); db.add(row)
    db.add(AuditEvent(actor=x_opspulse_user_email or "system", action="on_call_schedule.saved", resource_type="team", resource_id=str(body.team_id), organization_id=org_id))
    db.commit(); db.refresh(row)
    return {"id": row.id, "team_id": row.team_id, "name": row.name, "members": row.members, "rotation_hours": row.rotation_hours, "enabled": row.enabled}

@router.get("/escalation")
def policies(x_opspulse_organization_id: int | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _organization_id(x_opspulse_organization_id)
    rows = db.execute(select(EscalationPolicy, Team).join(Team, EscalationPolicy.team_id == Team.id).where(Team.organization_id == org_id)).all()
    return [{"id": row.id, "team_id": row.team_id, "name": row.name, "rules": row.rules, "enabled": row.enabled} for row, team in rows]

@router.post("/escalation", status_code=201)
def save_policy(body: PolicyInput, x_opspulse_organization_id: int | None = Header(default=None), x_opspulse_user_email: str | None = Header(default=None), db: Session = Depends(get_db)):
    org_id = _organization_id(x_opspulse_organization_id)
    if not db.scalar(select(Team).where(Team.id == body.team_id, Team.organization_id == org_id)):
        raise HTTPException(404, "Team not found")
    row = db.scalar(select(EscalationPolicy).where(EscalationPolicy.team_id == body.team_id))
    values = body.model_dump()
    values["rules"] = [rule.model_dump() for rule in body.rules]
    if row:
        row.name = values["name"]; row.rules = values["rules"]; row.enabled = values["enabled"]
    else:
        row = EscalationPolicy(**values); db.add(row)
    db.add(AuditEvent(actor=x_opspulse_user_email or "system", action="escalation_policy.saved", resource_type="team", resource_id=str(body.team_id), organization_id=org_id))
    db.commit(); db.refresh(row)
    return {"id": row.id, "team_id": row.team_id, "name": row.name, "rules": row.rules, "enabled": row.enabled}
