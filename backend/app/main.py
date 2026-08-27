# Main FastAPI Application — with security middleware, rate limiting, audit log

# Docling model compilation must be disabled before any docling import:
# CPU-only torch in the containers can't JIT-compile the CUDA kernels the
# compile_model path tries to emit, and the compile happens on the first
# conversion (torch._dynamo) which 500s the OCR request. The env var is
# read by pydantic-settings at module import time, so it has to be set
# here, before app.routers (which transitively imports document_parser).
import os as _os

_os.environ.setdefault("DOCLING_INFERENCE_COMPILE_TORCH_MODELS", "false")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.database import close_db, init_db
from app.dependencies import rate_limit_key
from app.middleware import audit_log_middleware, doctor_identity_middleware
from app.routers import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle.

    P0.8 — Preload work that would otherwise happen on the first (unlucky)
    request:
      * Embedding models (MedCPT + BGE-M3 + BiomedCLIP) — cold-load is
        ~4-8s and used to hit whichever doctor queried first.
      * The arq Redis pool used by every enqueue_* call.
      * The Playwright persistent browser (P0.6) used by PDF generators.
    All preloads are fire-and-forget: if any fails (e.g. Redis down at
    startup), the app still boots and lazy-loads on demand.
    """
    import asyncio as _asyncio
    import logging as _logging

    _log = _logging.getLogger(__name__)

    # Core dependencies (blocking — must succeed)
    await init_db()
    from app.routers.portal import ws_manager

    await ws_manager.start_subscriber()

    # ── P0.8 warm-ups (best-effort, run in parallel so startup stays fast) ──
    async def _warm_embeddings():
        try:
            from app.services.embeddings import embedding_service

            # _load_model is the single lazy-loader; passing each name pre-warms
            # its underlying SentenceTransformer / BGEM3FlagModel / open_clip.
            await _asyncio.gather(
                _asyncio.to_thread(embedding_service._load_model, "medcpt"),
                _asyncio.to_thread(embedding_service._load_model, "bge-m3"),
                _asyncio.to_thread(embedding_service._load_model, "biomedclip"),
                return_exceptions=True,
            )
            _log.info("Embedding models preloaded (P0.8)")
        except Exception as exc:
            _log.warning("Embedding preload failed (will lazy-load): %s", exc)

    async def _warm_arq():
        try:
            from app.services.background_jobs import preload_arq_pool

            await preload_arq_pool()
            _log.info("arq pool preloaded (P0.8)")
        except Exception as exc:
            _log.warning("arq preload failed (will lazy-init on first enqueue): %s", exc)

    async def _warm_browser():
        try:
            from app.services.pdf_generator import PDFGenerator

            await PDFGenerator._get_browser()
            _log.info("Playwright browser preloaded (P0.6/P0.8)")
        except Exception as exc:
            _log.warning("Playwright preload failed (will lazy-init on first PDF): %s", exc)

    # Fire in parallel so worst-case startup ≈ slowest single warm-up (~6s),
    # not sum-of-warm-ups (~15s).
    _asyncio.create_task(_warm_embeddings())
    _asyncio.create_task(_warm_arq())
    _asyncio.create_task(_warm_browser())

    yield

    # Shutdown
    await ws_manager.stop_subscriber()
    try:
        from app.services.pdf_generator import PDFGenerator

        await PDFGenerator.shutdown()
    except Exception:
        pass
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
