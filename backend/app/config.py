# Configuration

import sys

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "SoloPrac AI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Database
    POSTGRES_USER: str = "soloprac"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "soloprac"

    # Runtime DB role — a NON-OWNER, NON-SUPERUSER login subject to RLS.
    # The RLS policies (see app/migrations/rls_setup.sql) filter every query
    # through app.current_doctor_id / app.current_user_id; connecting as the
    # table-owner superuser would silently bypass them.
    APP_DB_USER: str = "soloprac_app"
    APP_DB_PASSWORD: str = "soloprac_app_dev_password_change_me"

    @property
    def DATABASE_URL(self) -> str:
        """Runtime connection — soloprac_app (RLS enforced)."""
        return f"postgresql+asyncpg://{self.APP_DB_USER}:{self.APP_DB_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def MIGRATION_DATABASE_URL(self) -> str:
        """Privileged connection (table owner / superuser) for init_db() and
        Alembic DDL. RLS does not apply to this role, which is correct for
        schema migrations — but this URL must NEVER be used for runtime
        sessions."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    DB_ECHO: bool = False
    # P1.13 — bumped from 10/20 to 25/50 per uvicorn worker.
    # With 4 workers that's 100 base + 200 overflow = 300 max Postgres connections,
    # which is comfortably under Postgres's default max_connections (100) after
    # accounting for other services (Langfuse, arq worker) — see init-schema.sql
    # for the matching max_connections bump. Sized for ~30 concurrent doctors
    # × ~2-3 in-flight queries each + fan-out (P1.12 uses its own session per
    # subquery, so 4 timeline sub-queries = 4 pool checkouts).
    DB_POOL_SIZE: int = 25
    DB_MAX_OVERFLOW: int = 50

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334

    # JWT
    JWT_SECRET_KEY: str = "changeme_generate_strong_secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 30
    JWT_REFRESH_EXPIRATION_DAYS: int = 7

    # ABDM Sandbox (Doctor Verification)
    ABDM_CLIENT_ID: str = ""
    ABDM_CLIENT_SECRET: str = ""
    ABDM_BASE_URL: str = "https://abdm.gov.in"

    # NMC / State Medical Council Verification
    NMC_API_URL: str = ""  # Indian Medical Register API endpoint (leave empty to skip)
    NMC_API_KEY: str = ""  # API key for NMC verification

    # NVIDIA NIM
    NIM_API_KEY: str = ""
    NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    MAVERICK_MODEL: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    LLAMA_8B_MODEL: str = "nvidia/llama-3.1-8b-instruct"
    # Some free-tier NIM models hang on `response_format=json_object`.
    # When False, structured outputs are still requested but the flag is
    # omitted so the call returns promptly (JSON is parsed leniently).
    MAVERICK_STRUCTURED_OUTPUT: bool = True
    BIOMEDCLIP_MODEL: str = "microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
    NVCLIP_MODEL: str = ""  # Deprecated — use NANONETS_OCR_MODEL instead

    # Groq
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    # Model used by the Groq fallback path. This is deliberately NOT
    # VISION_MODEL (google/medgemma-4b-it) — that model does not exist on
    # Groq and 404s; Groq serves its own llama-3.3-70b-versatile instead.
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    # Vision: MedGemma-4B-IT (local) for medical; fallback to Groq if needed
    VISION_MODEL: str = "google/medgemma-4b-it"

    # Local models
    MEDGEMMA_PATH: str = "/models/medgemma-gguf/medgemma-4b-it_Q4_K_M.gguf"
    MEDGEMMA_SERVER_URL: str = "http://llama-server:8080"
    WHISPER_PATH: str = "/hf_cache/faster-whisper-large-v3"
    INDIC_WHISPER_PATH: str = "/hf_cache/indic-whisper"
    PARLER_TTS_PATH: str = "/hf_cache/parler-tts-mini-v1.1"
    KOKORO_TTS_PATH: str = "/hf_cache/kokoro-onnx"
    KOKORO_TTS_VOICE: str = "af_bella"
    MMS_TTS_PATH: str = "/hf_cache/mms-tts-hin"
    MEDCPT_QUERY_PATH: str = "/hf_cache/MedCPT-Query-Encoder"
    MEDCPT_ARTICLE_PATH: str = "/hf_cache/MedCPT-Article-Encoder"
    BGE_M3_PATH: str = "/hf_cache/bge-m3"
    BIOMEDCLIP_PATH: str = "/hf_cache/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"

    # OCR
    NANONETS_OCR_MODEL: str = "nanonets/Nanonets-OCR2-1.5B-exp"

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "SoloPrac AI <noreply@soloprac.ai>"

    # Encryption
    ENCRYPTION_KEY: str = ""  # 32 bytes hex for pgcrypto/age

    # Caddy
    DOMAIN: str = "localhost"
    PORT: int = 8000  # Backend port (used in verify URLs and redirect URIs)
    ACME_EMAIL: str = "admin@soloprac.ai"

    # Rate limiting
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # Retrieval
    RETRIEVAL_TOP_K: int = 8  # Number of versions retrieved per query (configurable from backend)

    # MinIO / S3 Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "soloprac"
    MINIO_USE_HTTPS: bool = False

    # Langfuse
    LANGFUSE_HOST: str = "http://localhost:3000"
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""

    # Frontend URL (for CORS)
    FRONTEND_URL: str = "http://localhost:5173"

    # Admin access
    ADMIN_EMAILS: str = "admin@soloprac.io"  # Comma-separated list of admin emails

    # Sentry Error Tracking (free tier: 5k errors/month)
    SENTRY_DSN: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()

# ─── Startup validation: warn on default secrets ───
_DEFAULTS_WARNED = False
if not _DEFAULTS_WARNED:
    _DEFAULTS_WARNED = True
    if settings.JWT_SECRET_KEY in ("changeme_generate_strong_secret", ""):
        print(
            "WARNING: JWT_SECRET_KEY is still set to a default/empty value! Set a strong secret in .env",
            file=sys.stderr,
        )
    if not settings.ENCRYPTION_KEY:
        print(
            "WARNING: ENCRYPTION_KEY is empty! PII encryption will fail at runtime. Set a 32-byte hex key in .env",
            file=sys.stderr,
        )
    if settings.POSTGRES_PASSWORD in ("changeme", "soloprac_dev_password_change_me", ""):
        print(
            "WARNING: POSTGRES_PASSWORD is still a default! Change it in .env for any non-local deployment.",
            file=sys.stderr,
        )


def get_settings() -> Settings:
    return settings
