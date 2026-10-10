from __future__ import annotations
from urllib.parse import urlsplit
from pydantic import ValidationError
from fastapi import HTTPException
from shared.event_schemas import AlertPayload


def _failure(status: int, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"result": "failure", "message": message})


def validate_payload(data: dict) -> dict:
    # The source integration accepts upper-case message types. Normalizing also
    # accommodates monitoring clients whose examples send lowercase values.
    normalized = dict(data)
    if isinstance(normalized.get("message_type"), str):
        normalized["message_type"] = normalized["message_type"].upper()
    try:
        payload = AlertPayload.model_validate(normalized)
    except ValidationError as exc:
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        message = "Invalid alert payload" if not fields else f"Invalid alert payload fields: {', '.join(fields)}"
        raise _failure(400, message) from exc

    clean = payload.model_dump(exclude_none=True)
    for key, value in clean.items():
        if key.startswith("vo_annotate.s."):
            if not isinstance(value, str):
                raise _failure(422, f"Annotation '{key}' must be text")
            if len(value) > 1124:
                raise _failure(422, f"Annotation '{key}' exceeds 1124 characters")
        if key.startswith(("vo_annotate.u.", "vo_annotate.i.")):
            if not isinstance(value, str):
                raise _failure(422, f"Annotation '{key}' must contain an HTTP(S) URL")
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise _failure(422, f"Annotation '{key}' must contain a valid HTTP(S) URL")
    return {**normalized, **clean}
