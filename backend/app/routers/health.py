# Health Check Router

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import HealthCheck
from app.database import get_db
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db)):
    services = {}

    # Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        services["postgres"] = "up"
    except Exception:
        services["postgres"] = "down"

    # Qdrant check would be here when client is initialized
    services["qdrant"] = "not_configured_yet"
    services["redis"] = "not_configured_yet"
    services["langfuse"] = "not_configured_yet"

    return HealthCheck(
        status="healthy" if all(v == "up" for v in services.values()) else "degraded",
        version=settings.APP_VERSION,
        services=services,
    )


@router.get("/health/ready")
async def readiness_check():
    """Kubernetes readiness probe endpoint."""
    return {"status": "ready"}


@router.get("/health/live")
async def liveness_check():
    """Kubernetes liveness probe endpoint."""
    return {"status": "alive"}