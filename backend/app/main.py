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
    yield
    # Shutdown
    await close_db()


# Rate limiter
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=["100/minute"],
)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── Middleware Stack (order matters!) ──

# 1. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:5174"],
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

# 4. Doctor identity (RLS session variable)
app.middleware("http")(doctor_identity_middleware)

# 5. Audit log + security headers
app.middleware("http")(audit_log_middleware)

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
