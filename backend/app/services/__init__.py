"""Backend Services — centralized exports."""

from app.services.redis import redis_service, RedisService
from app.services.embeddings import embedding_service, EmbeddingService
from app.services.qdrant import qdrant_service, QdrantService
from app.services.indexer import index_version, index_version_job, WorkerSettings
from app.services.encryption import encrypt_value, decrypt_value, EncryptionService
from app.services.audit import (
    verify_rls_isolation,
    verify_audit_completeness,
    verify_optimistic_locking,
    run_security_audit,
)
from app.services.sanitizer import (
    sanitize_ocr_text,
    detect_injection,
    strip_suspicious_content,
    validate_structured_output,
    safe_parse_json,
    PrescriptionSchema,
    AppointmentSchema,
    WeeklyReportSchema,
)

__all__ = [
    "redis_service",
    "RedisService",
    "embedding_service",
    "EmbeddingService",
    "qdrant_service",
    "QdrantService",
    "index_version",
    "index_version_job",
    "WorkerSettings",
    "encrypt_value",
    "decrypt_value",
    "EncryptionService",
    "verify_rls_isolation",
    "verify_audit_completeness",
    "verify_optimistic_locking",
    "run_security_audit",
    "sanitize_ocr_text",
    "detect_injection",
    "strip_suspicious_content",
    "validate_structured_output",
    "safe_parse_json",
    "PrescriptionSchema",
    "AppointmentSchema",
    "WeeklyReportSchema",
]