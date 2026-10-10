from sqlalchemy import select, desc
from shared.models import AuditEvent

def list_events(db, limit:int=100, organization_id:int|None=None):
    query=select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(max(1,min(limit,1000)))
    if organization_id: query=select(AuditEvent).where(AuditEvent.organization_id==organization_id).order_by(desc(AuditEvent.created_at)).limit(max(1,min(limit,1000)))
    rows=db.scalars(query).all()
    return [{"id":x.id,"actor":x.actor,"action":x.action,"resource_type":x.resource_type,"resource_id":x.resource_id,"details":x.details,"created_at":x.created_at.isoformat()} for x in rows]
