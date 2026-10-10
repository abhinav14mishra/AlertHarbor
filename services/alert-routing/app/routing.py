import hashlib
from sqlalchemy import select
from fastapi import HTTPException
from shared.models import RoutingKey


def resolve_routing_key(db, key: str):
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    row = db.scalar(select(RoutingKey).where(RoutingKey.key_hash == digest, RoutingKey.enabled.is_(True)))
    if not row:
        raise HTTPException(status_code=401, detail={"result": "failure", "message": "Invalid or revoked routing key"})
    return row
