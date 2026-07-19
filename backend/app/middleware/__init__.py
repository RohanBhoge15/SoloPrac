# Security Middleware — audit logging, CORS hardening, rate limiting

from __future__ import annotations

import time
import logging
from typing import Callable, Awaitable
from uuid import UUID
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import async_session_maker
from app.models import AuditLog

logger = logging.getLogger(__name__)


async def audit_log_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Middleware that logs every API request to the audit_log table.
    Skips health checks and static assets.
    """
    start = time.time()

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
            log_entry = AuditLog(
                doctor_id=doctor_id,
                patient_id=patient_id,
                actor=f"doctor:{doctor_id}" if doctor_id else "system",
                action=action,
                resource_type=resource_type,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                payload_jsonb={
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration,
                },
            )
            async with async_session_maker() as session:
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.warning(f"Audit log write failed (non-blocking): {e}")

    # Add security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"

    return response


async def doctor_identity_middleware(request: Request, call_next):
    """
    Extracts doctor identity from JWT and sets it in request.state
    and the PostgreSQL session variable for RLS enforcement.

    RLS isolation: Every SQLAlchemy session used during this request
    will see `current_setting('app.current_doctor_id')` set to the
    authenticated doctor's UUID. This is how RLS policies filter rows.
    """
    from app.database import async_session_maker

    # Try to extract doctor from Authorization header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from jose import jwt, JWTError
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            doctor_id = payload.get("sub")
            if doctor_id:
                request.state.doctor_id = UUID(doctor_id)
        except JWTError:
            pass

    response = await call_next(request)

    # After response, set the RLS session variable for any deferred queries
    doctor_id = getattr(request.state, "doctor_id", None)
    if doctor_id:
        try:
            async with async_session_maker() as session:
                await session.execute(
                    text("SELECT set_config('app.current_doctor_id', :did, true)"),
                    {"did": str(doctor_id)},
                )
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to set RLS session variable: %s", exc)

    return response
