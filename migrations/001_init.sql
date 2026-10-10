-- OpsPulse PostgreSQL initial schema (apply once to an empty database).
-- The local Docker Compose profile may use SQLAlchemy create_all for convenience;
-- production environments should apply versioned SQL migrations before deploying code.

CREATE TABLE IF NOT EXISTS organizations (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_organizations_name ON organizations(name);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    display_name VARCHAR(160) NOT NULL DEFAULT '',
    role VARCHAR(40) NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_organization_id ON users(organization_id);

CREATE TABLE IF NOT EXISTS teams (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_teams_name ON teams(name);
CREATE INDEX IF NOT EXISTS ix_teams_organization_id ON teams(organization_id);

CREATE TABLE IF NOT EXISTS routing_keys (
    id BIGSERIAL PRIMARY KEY,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_prefix VARCHAR(12) NOT NULL DEFAULT '',
    team_id BIGINT NOT NULL REFERENCES teams(id),
    name VARCHAR(120) NOT NULL DEFAULT 'Default integration',
    warnings_enabled BOOLEAN NOT NULL DEFAULT true,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_routing_keys_key_hash ON routing_keys(key_hash);

CREATE TABLE IF NOT EXISTS incidents (
    id BIGSERIAL PRIMARY KEY,
    incident_key VARCHAR(64) NOT NULL UNIQUE,
    entity_id VARCHAR(256) NOT NULL,
    entity_display_name VARCHAR(256) NOT NULL DEFAULT '',
    state_message TEXT NOT NULL DEFAULT '',
    message_type VARCHAR(32) NOT NULL DEFAULT 'CRITICAL',
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    team_id BIGINT NOT NULL REFERENCES teams(id),
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    routing_key_id BIGINT NOT NULL REFERENCES routing_keys(id),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    annotations JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ NULL,
    resolved_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS ix_incidents_incident_key ON incidents(incident_key);
CREATE INDEX IF NOT EXISTS ix_incidents_entity_id ON incidents(entity_id);
CREATE INDEX IF NOT EXISTS ix_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS ix_incidents_organization_id ON incidents(organization_id);
CREATE INDEX IF NOT EXISTS ix_incident_entity_status ON incidents(entity_id, status);

CREATE TABLE IF NOT EXISTS timeline_events (
    id BIGSERIAL PRIMARY KEY,
    incident_id BIGINT NULL REFERENCES incidents(id),
    entity_id VARCHAR(256) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    actor VARCHAR(320) NOT NULL DEFAULT 'system',
    message TEXT NOT NULL DEFAULT '',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_timeline_events_incident_id ON timeline_events(incident_id);
CREATE INDEX IF NOT EXISTS ix_timeline_events_entity_id ON timeline_events(entity_id);

CREATE TABLE IF NOT EXISTS on_call_schedules (
    id BIGSERIAL PRIMARY KEY,
    team_id BIGINT NOT NULL UNIQUE REFERENCES teams(id),
    name VARCHAR(120) NOT NULL,
    members JSONB NOT NULL DEFAULT '[]'::jsonb,
    rotation_hours INTEGER NOT NULL DEFAULT 168,
    enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS escalation_policies (
    id BIGSERIAL PRIMARY KEY,
    team_id BIGINT NOT NULL UNIQUE REFERENCES teams(id),
    name VARCHAR(120) NOT NULL,
    rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NULL REFERENCES organizations(id),
    actor VARCHAR(320) NOT NULL DEFAULT 'system',
    action VARCHAR(120) NOT NULL,
    resource_type VARCHAR(80) NOT NULL,
    resource_id VARCHAR(128) NOT NULL DEFAULT '',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_events_organization_id ON audit_events(organization_id);

CREATE TABLE IF NOT EXISTS outbox_events (
    id BIGSERIAL PRIMARY KEY,
    event_key VARCHAR(64) NOT NULL UNIQUE,
    topic VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ NULL,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_outbox_events_event_key ON outbox_events(event_key);
CREATE INDEX IF NOT EXISTS ix_outbox_events_topic ON outbox_events(topic);
CREATE INDEX IF NOT EXISTS ix_outbox_pending ON outbox_events(published_at, available_at);

CREATE TABLE IF NOT EXISTS notification_deliveries (
    id BIGSERIAL PRIMARY KEY,
    event_key VARCHAR(64) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    sent_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_notification_event_recipient UNIQUE (event_key, recipient)
);
CREATE INDEX IF NOT EXISTS ix_notification_deliveries_event_key ON notification_deliveries(event_key);
CREATE INDEX IF NOT EXISTS ix_notification_deliveries_status ON notification_deliveries(status);


CREATE TABLE IF NOT EXISTS escalation_tasks (
    id BIGSERIAL PRIMARY KEY,
    task_key VARCHAR(64) NOT NULL UNIQUE,
    source_event_key VARCHAR(64) NOT NULL,
    rule_index INTEGER NOT NULL,
    team_id BIGINT NOT NULL REFERENCES teams(id),
    incident_key VARCHAR(64) NOT NULL,
    recipients JSONB NOT NULL DEFAULT '[]'::jsonb,
    due_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ NULL,
    CONSTRAINT uq_escalation_source_rule UNIQUE (source_event_key, rule_index)
);
CREATE INDEX IF NOT EXISTS ix_escalation_tasks_task_key ON escalation_tasks(task_key);
CREATE INDEX IF NOT EXISTS ix_escalation_tasks_source_event_key ON escalation_tasks(source_event_key);
CREATE INDEX IF NOT EXISTS ix_escalation_tasks_incident_key ON escalation_tasks(incident_key);
CREATE INDEX IF NOT EXISTS ix_escalation_due ON escalation_tasks(status, due_at);
