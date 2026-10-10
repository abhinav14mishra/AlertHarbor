from __future__ import annotations
import json
import os
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from shared.config import INTERNAL_API_TOKEN, MAX_ALERT_BODY_BYTES
from shared.database import get_db
from app.validators import validate_payload
from app.routing import resolve_routing_key
from app.response import success

router = APIRouter()
INCIDENT_URL = os.getenv("INCIDENT_URL", "http://incident:8000").rstrip("/")


async def _receive(request: Request, routing_key: str | None, db: Session) -> dict:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_ALERT_BODY_BYTES:
                raise HTTPException(status_code=413, detail={"result": "failure", "message": "Request body is too large"})
        except ValueError:
            raise HTTPException(status_code=400, detail={"result": "failure", "message": "Invalid Content-Length header"})
    raw = await request.body()
    if len(raw) > MAX_ALERT_BODY_BYTES:
        raise HTTPException(status_code=413, detail={"result": "failure", "message": "Request body is too large"})
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"result": "failure", "message": "Request body must be valid JSON"}) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail={"result": "failure", "message": "Request body must be a JSON object"})
    payload = validate_payload(data)
    if not routing_key:
        raise HTTPException(status_code=400, detail={"result": "failure", "message": "Missing routing key; supply x-alert-harbor-routing-key"})
    key = resolve_routing_key(db, routing_key)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as client:
            response = await client.post(
                f"{INCIDENT_URL}/internal/ingest",
                json={"routing_key_id": key.id, "payload": payload},
                headers={"X-Internal-Service-Token": INTERNAL_API_TOKEN},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail={"result": "failure", "message": "Incident service timed out; retry the same entity_id"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"result": "failure", "message": "Incident service is unavailable"}) from exc
    try:
        result = response.json()
    except ValueError:
        result = {"result": "failure", "message": "Incident service returned an invalid response"}
    if response.status_code >= 400:
        detail = result.get("detail", result) if isinstance(result, dict) else {"result": "failure", "message": "Incident service rejected the event"}
        raise HTTPException(status_code=response.status_code, detail=detail)
    return success(result)


@router.post("/api/events")
async def receive_event(
    request: Request,
    x_alert_harbor_routing_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    return await _receive(request, x_alert_harbor_routing_key, db)


@router.post("/v1/alerts/{routing_key}")
async def receive_alert(routing_key: str, request: Request, db: Session = Depends(get_db)):
    return await _receive(request, routing_key, db)
