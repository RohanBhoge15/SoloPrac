# Security Middleware — audit logging, CORS hardening, rate limiting, request tracing

from __future__ import annotations

import logging
import time
import uuid
from typing import Awaitable, Callable
from uuid import UUID

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import async_session_maker
from app.models import AuditLog

logger = logging.getLogger(__name__)

# Map URL prefixes to resource types (more robust than path splitting)
RESOURCE_TYPE_MAP = {
    "/api/v1/patients": "patient",
    "/api/v1/auth": "auth",
    "/api/v1/agent": "agent",
    "/api/v1/images": "image",
    "/api/v1/evaluation": "evaluation",
    "/api/v1/documents": "document",
    "/api/v1/security": "security",
    "/api/v1/prescriptions": "prescription",
    "/api/v1/certificates": "certificate",
    "/api/v1/invoices": "invoice",
    "/api/v1/calendar": "calendar",
    "/api/v1/portal": "portal",
    "/api/v1/weekly_report": "weekly_report",
    "/api/v1/risk-alerts": "risk_alert",
    "/api/v1/admin": "admin",
    "/api/v1/health": "health",
}


def _get_resource_type(path: str) -> str:
    """Determine resource type from URL prefix (robust against path changes)."""
    for prefix, resource in RESOURCE_TYPE_MAP.items():
        if path.startswith(prefix):
            return resource
    return "unknown"


def _get_client_ip(request: Request) -> str | None:
    """Extract real client IP from X-Forwarded-For header (behind proxy)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


async def audit_log_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Middleware that logs every API request to the audit_log table.
    Skips health checks and static assets.
    """
    start = time.time()

    # Assign request correlation ID for tracing
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id

    # Skip audit for non-tracked paths
    path = request.url.path
    if (
        path in ("/api/v1/health", "/api/v1/health/ready", "/api/v1/health/live", "/")
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi.json")
    ):
        return await call_next(request)

    response: Response = await call_next(request)
    duration = round((time.time() - start) * 1000)

    # Get doctor_id from request state (set by auth)
    doctor_id = getattr(request.state, "doctor_id", None)
    patient_id = getattr(request.state, "patient_id", None)

    # Only log mutations and meaningful reads
    action_map = {
        "POST": "write",
        "PUT": "write",
        "PATCH": "write",
        "DELETE": "write",
        "GET": "read",
    }
    action = action_map.get(request.method, "read")

    # Determine resource type from URL prefix (robust)
    resource_type = _get_resource_type(path)

    # Fire-and-forget audit log (don't block the response)
    if doctor_id and action in ("write", "read"):
        try:
            from app.database import _current_doctor_id

            log_entry = AuditLog(
                doctor_id=doctor_id,
                patient_id=patient_id,
                actor=f"doctor:{doctor_id}" if doctor_id else "system",
                action=action,
                resource_type=resource_type,
                ip_address=_get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                payload_jsonb={
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration,
                    "request_id": getattr(request.state, "request_id", None),
                },
            )
            async with async_session_maker() as session:
                # Set RLS variable on audit session so INSERT passes RLS
                if doctor_id:
                    await session.execute(
                        text("SELECT set_config('app.current_doctor_id', :did, true)"),
                        {"did": str(doctor_id)},
                    )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.warning(f"Audit log write failed (non-blocking): {e}")

    # Add security headers + request ID
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=(self)"
    response.headers["X-Request-ID"] = request_id

    return response


async def doctor_identity_middleware(request: Request, call_next):
    """
    Extracts doctor AND patient identity from JWT and stores them in context
    variables for RLS enforcement. The actual set_config call happens in
    get_db() on the session the route handler uses.

    Doctor tokens (type access/refresh) -> app.current_doctor_id
    Patient tokens (type patient)       -> app.current_user_id
    """
    from app.database import _current_doctor_id, _current_user_id

    doctor_id = None
    user_id = None

    def _consume_token(token: str):
        nonlocal doctor_id, user_id
        try:
            from jose import JWTError, jwt

            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            token_type = payload.get("type", "access")
            sub = payload.get("sub")
            if not sub:
                return
            if token_type in ("access", "refresh"):
                doctor_id = sub
                request.state.doctor_id = UUID(sub)
                # Store decoded payload to avoid double-decode in get_current_doctor
                request.state.token_payload = payload
            elif token_type == "patient":
                user_id = sub
                request.state.user_id = UUID(sub)
        except JWTError:
            pass

    # Authorization header first, HttpOnly cookies as fallback
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        _consume_token(auth[7:])
    if not doctor_id and not user_id:
        _consume_token(request.cookies.get("access_token", ""))
    if not doctor_id and not user_id:
        _consume_token(request.cookies.get("patient_token", ""))

    # Store identity in context vars so get_db() can set them on the session
    did_token = _current_doctor_id.set(doctor_id)
    uid_token = _current_user_id.set(user_id)

    try:
        response = await call_next(request)
    finally:
        _current_doctor_id.reset(did_token)
        _current_user_id.reset(uid_token)

    return response
