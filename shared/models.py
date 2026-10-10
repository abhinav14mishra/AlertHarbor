from datetime import datetime, timezone
import secrets
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base

def now_utc(): return datetime.now(timezone.utc)

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(160), default="")
    role: Mapped[str] = mapped_column(String(40), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class RoutingKey(Base):
    __tablename__ = "routing_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(12), default="")
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String(120), default="Default integration")
    warnings_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incident_entity_status", "entity_id", "status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: secrets.token_urlsafe(18))
    entity_id: Mapped[str] = mapped_column(String(256), index=True)
    entity_display_name: Mapped[str] = mapped_column(String(256), default="")
    state_message: Mapped[str] = mapped_column(Text, default="")
    message_type: Mapped[str] = mapped_column(String(32), default="CRITICAL")
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    routing_key_id: Mapped[int] = mapped_column(ForeignKey("routing_keys.id"))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    annotations: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True, index=True)
    entity_id: Mapped[str] = mapped_column(String(256), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(320), default="system")
    message: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class OnCallSchedule(Base):
    __tablename__ = "on_call_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    members: Mapped[list] = mapped_column(JSON, default=list)
    rotation_hours: Mapped[int] = mapped_column(Integer, default=168)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class EscalationPolicy(Base):
    __tablename__ = "escalation_policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    rules: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(320), default="system")
    action: Mapped[str] = mapped_column(String(120))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(128), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class OutboxEvent(Base):
    """Durable transactional outbox; the worker publishes committed events at least once."""
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_pending", "published_at", "available_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: secrets.token_urlsafe(24))
    topic: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class NotificationDelivery(Base):
    """Idempotency ledger for outbound notifications per event and recipient."""
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("event_key", "recipient", name="uq_notification_event_recipient"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(64), index=True)
    recipient: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EscalationTask(Base):
    """A delayed, durable escalation step scheduled from an incident trigger."""
    __tablename__ = "escalation_tasks"
    __table_args__ = (
        UniqueConstraint("source_event_key", "rule_index", name="uq_escalation_source_rule"),
        Index("ix_escalation_due", "status", "due_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: secrets.token_urlsafe(24))
    source_event_key: Mapped[str] = mapped_column(String(64), index=True)
    rule_index: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    incident_key: Mapped[str] = mapped_column(String(64), index=True)
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
