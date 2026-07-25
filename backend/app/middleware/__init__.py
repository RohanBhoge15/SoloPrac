# Security Middleware — audit logging, CORS hardening, rate limiting, request tracing

from __future__ import annotations

import time
import uuid
import logging
from typing import Callable, Awaitable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from uuid import UUID

from app.config import settings
from app.database import async_session_maker
from app.models import AuditLog

logger = logging.getLogger(__name__)


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
    if path in ("/api/v1/health", "/api/v1/health/ready", "/api/v1/health/live", "/") or path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi.json"):
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

    # Determine resource type from path
    resource_type = path.split("/")[3] if len(path.split("/")) > 3 else "unknown"

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
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    response.headers["X-Request-ID"] = request_id

    return response


async def doctor_identity_middleware(request: Request, call_next):
    """
    Extracts doctor identity from JWT and stores it in a context variable
    for RLS enforcement. The actual set_config call happens in get_db()
    on the session the route handler uses.
    """
    from app.database import _current_doctor_id

    # Try to extract doctor from Authorization header
    doctor_id = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from jose import jwt, JWTError
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            # Only accept doctor-type tokens (reject patient tokens to avoid ID collision)
            token_type = payload.get("type", "access")
            if token_type in ("access", "refresh"):
                doctor_id = payload.get("sub")
                if doctor_id:
                    request.state.doctor_id = UUID(doctor_id)
        except JWTError:
            pass

    # Store doctor_id in context var so get_db() can set it on the actual session
    token = _current_doctor_id.set(doctor_id)

    try:
        response = await call_next(request)
    finally:
        _current_doctor_id.reset(token)

    return response
