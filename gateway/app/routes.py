from __future__ import annotations
from fastapi import APIRouter, Request, Response, HTTPException
import httpx
import logging
import os
import time
from shared.config import APP_ENV
from app.config import SERVICE_URLS
from shared.security import decode_token

router = APIRouter()
PREFIXES = {
    "auth": "identity", "organizations": "organization", "teams": "organization", "routing-keys": "organization",
    "incidents": "incidents", "alerts": "alerts", "on-call": "escalation",
    "escalation": "escalation", "audit": "audit",
}
PUBLIC_AUTH_PATHS = {("auth", "login"), ("auth", "register")}
ADMIN_PREFIXES = {"organizations", "teams", "routing-keys", "on-call", "escalation", "users"}
logger = logging.getLogger("opspulse.gateway")
_redis = None


def _rate_limit_auth(request: Request, route: str) -> None:
    client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
    window = int(time.time() // 60)
    key = f"opspulse:rate:{route}:{client_ip}:{window}"
    limit = 10 if route == "login" else 5
    try:
        global _redis
        if _redis is None:
            import redis
            _redis = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
        count = _redis.incr(key)
        if count == 1:
            _redis.expire(key, 70)
    except Exception as exc:
        logger.warning("Auth rate limiter unavailable")
        if APP_ENV == "production":
            raise HTTPException(503, "Authentication service temporarily unavailable") from exc
        return
    if count > limit:
        raise HTTPException(429, "Too many authentication attempts; try again in a minute")


def _identity(request: Request) -> dict | None:
    authorization = request.headers.get("authorization", "")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Invalid Authorization header", headers={"WWW-Authenticate": "Bearer"})
    try:
        return decode_token(token)
    except ValueError as exc:
        raise HTTPException(401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}) from exc


def _authorize(request: Request, service: str, path: str) -> dict | None:
    # Routing keys are bearer secrets for monitoring systems; do not require a user JWT.
    if service == "alerts" and path.startswith("v1/alerts/"):
        return None
    if (service, path.strip("/")) in PUBLIC_AUTH_PATHS:
        _rate_limit_auth(request, path.strip("/"))
        return None
    user = _identity(request)
    if not user:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    if request.method not in {"GET", "HEAD", "OPTIONS"} and ((service in ADMIN_PREFIXES) or (service == "auth" and path.strip("/") == "users")) and user.get("role") != "admin":
        raise HTTPException(403, "Administrator role required")
    return user


async def _forward(request: Request, target: str, path: str, method: str | None = None, identity: dict | None = None):
    url = f"{SERVICE_URLS[target]}/{path}" if path else SERVICE_URLS[target]
    if request.url.query:
        url += f"?{request.url.query}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length", "connection", "x-opspulse-organization-id", "x-opspulse-user-email", "x-opspulse-role"}}
    if identity:
        headers["X-OpsPulse-Organization-Id"] = str(identity["organization_id"])
        headers["X-OpsPulse-User-Email"] = str(identity["sub"])
        headers["X-OpsPulse-Role"] = str(identity["role"])
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0)) as client:
            result = await client.request(method or request.method, url, content=body, headers=headers)
        response_headers = {k: v for k, v in result.headers.items() if k.lower() in {"content-type", "cache-control"}}
        return Response(content=result.content, status_code=result.status_code, headers=response_headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, f"Service timed out: {target}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Service unavailable: {target}") from exc


@router.api_route("/api/events", methods=["POST"])
async def rest_events(request: Request):
    """REST Endpoint compatibility route using the routing-key header."""
    return await _forward(request, "alerts", "api/events", "POST")


@router.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(service: str, path: str, request: Request):
    target = PREFIXES.get(service)
    if not target:
        raise HTTPException(404, "Unknown API service")
    identity = _authorize(request, service, path)
    return await _forward(request, target, path, identity=identity)
