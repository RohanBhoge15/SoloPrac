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
    sanitize_for_doc_type,
    strip_suspicious_content,
    validate_structured_output,
    safe_parse_json,
    PrescriptionSchema,
    AppointmentSchema,
    WeeklyReportSchema,
)
from app.services.temporal_rag import (
    TemporalMultimodalRetriever,
    temporal_decay,
    clinical_significance_from_tags,
    ALPHA, BETA, GAMMA, DELTA, EPSILON, TAU, TIER_WEIGHTS,
)
from app.services.evaluation import (
    EvaluationHarness,
    generate_test_dataset,
    compute_recall_at_k,
    compute_future_leak_rate,
    BM25Baseline,
)
from app.services.rag_audit import (
    RAGAuditService,
    LLMRateLimiter,
    validate_no_future_leak,
)
from app.services.image_registration import ImageRegistrationService, image_registration_service
from app.services.image_security import ImageSecurityService
from app.services.pdf_security import PDFSecurityService
from app.services.medical_formatter import MedicalFormatter
from app.services.calendar_service import CalendarService
from app.services.email_queue import email_queue
from app.services.voice_scheduler import voice_scheduler
from app.services.notification_prefs import validate_notification_prefs, get_enabled_channels, merge_with_defaults
from app.services.calendar_security import calendar_security, CalendarRateLimiter

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
    "TemporalMultimodalRetriever",
    "temporal_decay",
    "clinical_significance_from_tags",
    "ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON", "TAU", "TIER_WEIGHTS",
    "EvaluationHarness",
    "generate_test_dataset",
    "compute_recall_at_k",
    "compute_future_leak_rate",
    "BM25Baseline",
    "RAGAuditService",
    "LLMRateLimiter",
    "validate_no_future_leak",
    "ImageRegistrationService",
    "image_registration_service",
    "ImageSecurityService",
    "PDFSecurityService",
    "MedicalFormatter",
    "CalendarService",
    "email_queue",
    "voice_scheduler",
    "validate_notification_prefs",
    "get_enabled_channels",
    "merge_with_defaults",
    "calendar_security",
    "CalendarRateLimiter",
]