import os
SERVICE_URLS = {
 "identity": os.getenv("IDENTITY_URL", "http://identity:8000"),
 "organization": os.getenv("ORGANIZATION_URL", "http://organization:8000"),
 "incidents": os.getenv("INCIDENT_URL", "http://incident:8000"),
 "alerts": os.getenv("ALERT_ROUTING_URL", "http://alert-routing:8000"),
 "escalation": os.getenv("ESCALATION_URL", "http://escalation:8000"),
 "notifications": os.getenv("NOTIFICATION_URL", "http://notification:8000"),
 "audit": os.getenv("AUDIT_URL", "http://audit:8000"),
 "worker": os.getenv("WORKER_URL", "http://worker:8000"),
}
