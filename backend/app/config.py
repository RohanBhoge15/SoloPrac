# Configuration

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


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

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
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

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/callback/google"

    # NVIDIA NIM
    NIM_API_KEY: str = ""
    NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    MAVERICK_MODEL: str = "nvidia/llama-4-maverick-17b-128e-instruct"
    LLAMA_8B_MODEL: str = "nvidia/llama-3.1-8b-instruct"
    NVCLIP_MODEL: str = "nvidia/nv-clip"

    # Groq
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    VISION_MODEL: str = "llama-3.2-90b-vision-preview"

    # Local models
    MEDGEMMA_PATH: str = "/models/medgemma-4b-it"
    WHISPER_PATH: str = "/models/faster-whisper-large-v3"
    INDIC_WHISPER_PATH: str = "/models/indic-whisper"
    PARLER_TTS_PATH: str = "/models/indic-parler-tts"

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
    ACME_EMAIL: str = "admin@soloprac.ai"

    # Rate limiting
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # Langfuse
    LANGFUSE_HOST: str = "http://localhost:3000"
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""

    # Frontend URL (for CORS)
    FRONTEND_URL: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()