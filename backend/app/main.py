# Main FastAPI Application — with security middleware, rate limiting, audit log

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.database import init_db, close_db
from app.dependencies import rate_limit_key
from app.routers import api_router
from app.middleware import audit_log_middleware, doctor_identity_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    from app.routers.portal import ws_manager
    await ws_manager.start_subscriber()
    yield
    # Shutdown
    await ws_manager.stop_subscriber()
    await close_db()


# Rate limiter
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=["100/minute"],
)

# Sentry error tracking (free tier: 5k errors/month)
if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        environment="development" if settings.DEBUG else "production",
    )


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── Middleware Stack (order matters! LIFO — last added wraps first) ──

# 1. CORS
# Only allow FRONTEND_URL from settings (no hardcoded localhost in production)
cors_origins = [settings.FRONTEND_URL]
if settings.DEBUG:
    cors_origins.extend(["http://localhost:5173", "http://localhost:5174"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Current-Version", "X-Error-Code"],
)

# 2. Trusted hosts (only in production)
if not settings.DEBUG and settings.DOMAIN:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[settings.DOMAIN],
    )

# 3. Rate limiting (slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# 4. Audit log + security headers (wraps everything below)
app.middleware("http")(audit_log_middleware)

# 5. Doctor identity (RLS context var) — runs AFTER audit, BEFORE route handler
app.middleware("http")(doctor_identity_middleware)

# ── API Routes ──
app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/health")
async def public_health():
    return {"status": "ok", "version": settings.APP_VERSION}
