# Health Check Router

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import HealthCheck
from app.database import get_db
from app.config import get_settings
from app.services.qdrant import qdrant_service
from app.services.redis import redis_service

router = APIRouter()
settings = get_settings()


async def check_qdrant() -> str:
    """Check Qdrant connectivity."""
    try:
        client = await qdrant_service.connect()
        collections = client.get_collections()
        return "up" if collections is not None else "degraded"
    except Exception:
        return "down"


async def check_redis() -> str:
    """Check Redis connectivity."""
    try:
        client = await redis_service.connect()
        await client.ping()
        return "up"
    except Exception:
        return "down"


async def check_langfuse() -> str:
    """Check Langfuse connectivity."""
    try:
        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            return "not_configured"
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.LANGFUSE_HOST}/api/public/health")
            return "up" if resp.status_code == 200 else "degraded"
    except Exception:
        return "down"


@router.get("/health", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db)):
    services = {}

    # Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        services["postgres"] = "up"
    except Exception:
        services["postgres"] = "down"

    # Check Qdrant
    services["qdrant"] = await check_qdrant()

    # Check Redis
    services["redis"] = await check_redis()

    # Check Langfuse
    services["langfuse"] = await check_langfuse()

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