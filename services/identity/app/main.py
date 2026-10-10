from __future__ import annotations
import re
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import select, func, text
from shared.config import ALLOW_SELF_REGISTRATION
from shared.database import get_db, init_db
from shared.models import User, Organization, AuditEvent
from shared.security import hash_password, verify_password, create_token

app = FastAPI(title="OpsPulse Identity", version="1.0.0")

@app.on_event("startup")
def startup():
    init_db()

class Register(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=160)
    organization_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("A valid email address is required")
        return value

    @field_validator("display_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name is required")
        return value

class Login(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

@app.get("/health")
def health():
    return {"status": "ok", "service": "identity"}

@app.post("/register", status_code=201)
def register(body: Register, db: Session = Depends(get_db)):
    email = body.email
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(74120932)"))
    existing_count = db.scalar(select(func.count(User.id))) or 0
    if existing_count and not ALLOW_SELF_REGISTRATION:
        raise HTTPException(403, "Self-registration is disabled; ask an administrator to provision your account")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    organization = db.scalar(select(Organization).order_by(Organization.id).limit(1))
    if organization is None:
        org_name = (body.organization_name or f"{body.display_name}'s Workspace").strip()
        if not org_name:
            org_name = "Default Workspace"
        organization = Organization(name=org_name[:120])
        db.add(organization)
        db.flush()
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        organization_id=organization.id,
        role="admin" if existing_count == 0 else "member",
    )
    db.add(user)
    db.flush()
    db.add(AuditEvent(actor=email, action="user.registered", resource_type="user", resource_id=str(user.id), organization_id=organization.id, details={"organization_id": organization.id}))
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role, "organization_id": user.organization_id}

@app.post("/users", status_code=201)
def create_user(
    body: Register,
    x_opspulse_role: str | None = Header(default=None),
    x_opspulse_organization_id: int | None = Header(default=None),
    x_opspulse_user_email: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if x_opspulse_role != "admin" or not x_opspulse_organization_id or not x_opspulse_user_email:
        raise HTTPException(403, "Administrator role required")
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(409, "Email already registered")
    if not db.get(Organization, x_opspulse_organization_id):
        raise HTTPException(400, "Invalid organization context")
    user = User(email=body.email, password_hash=hash_password(body.password), display_name=body.display_name,
                organization_id=x_opspulse_organization_id, role="member")
    db.add(user); db.flush()
    db.add(AuditEvent(actor=x_opspulse_user_email, action="user.provisioned", resource_type="user", resource_id=str(user.id), organization_id=x_opspulse_organization_id, details={"organization_id": x_opspulse_organization_id}))
    db.commit(); db.refresh(user)
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role, "organization_id": user.organization_id}

@app.post("/login")
def login(body: Login, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    db.add(AuditEvent(actor=user.email, action="user.login", resource_type="user", resource_id=str(user.id), organization_id=user.organization_id))
    db.commit()
    return {
        "access_token": create_token(user.email, user.role, organization_id=user.organization_id),
        "token_type": "bearer", "expires_in": 3600,
        "user": {"email": user.email, "display_name": user.display_name, "role": user.role, "organization_id": user.organization_id},
    }
