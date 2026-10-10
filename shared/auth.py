"""Reusable FastAPI bearer-token dependencies for service-local protection."""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared.security import decode_token

_bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        return decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}) from exc


def administrator(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required")
    return user
