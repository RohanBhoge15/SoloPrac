"""Backend Services — centralized exports.

Uses lazy imports to break circular dependency chains:
  services → medical_formatter → synthesizer → agents/__init__ → tools → temporal_rag → services
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.redis import RedisService
    from app.services.embeddings import EmbeddingService
    from app.services.qdrant import QdrantService


class _LazyModule:
    """Lazy module proxy that defers import until first attribute access."""

    def __init__(self, module_path: str, attr_name: str):
        self._module_path = module_path
        self._attr_name = attr_name
        self._cached = None

    def _resolve(self):
        if self._cached is None:
            mod = importlib.import_module(self._module_path)
            self._cached = getattr(mod, self._attr_name)
        return self._cached

    def __getattr__(self, name):
        return getattr(self._resolve(), name)

    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)


def __getattr__(name: str):
    """Module-level __getattr__ for lazy imports."""
    _LAZY_IMPORTS = {
        "redis_service": ("app.services.redis", "redis_service"),
        "RedisService": ("app.services.redis", "RedisService"),
        "embedding_service": ("app.services.embeddings", "embedding_service"),
        "EmbeddingService": ("app.services.embeddings", "EmbeddingService"),
        "qdrant_service": ("app.services.qdrant", "qdrant_service"),
        "QdrantService": ("app.services.qdrant", "QdrantService"),
        "index_version": ("app.services.indexer", "index_version"),
        "index_version_job": ("app.services.indexer", "index_version_job"),
        "WorkerSettings": ("app.services.indexer", "WorkerSettings"),
        "encrypt_value": ("app.services.encryption", "encrypt_value"),
        "decrypt_value": ("app.services.encryption", "decrypt_value"),
        "EncryptionService": ("app.services.encryption", "EncryptionService"),
        "verify_rls_isolation": ("app.services.audit", "verify_rls_isolation"),
        "verify_audit_completeness": ("app.services.audit", "verify_audit_completeness"),
        "verify_optimistic_locking": ("app.services.audit", "verify_optimistic_locking"),
        "run_security_audit": ("app.services.audit", "run_security_audit"),
        "sanitize_ocr_text": ("app.services.sanitizer", "sanitize_ocr_text"),
        "detect_injection": ("app.services.sanitizer", "detect_injection"),
        "sanitize_for_doc_type": ("app.services.sanitizer", "sanitize_for_doc_type"),
        "strip_suspicious_content": ("app.services.sanitizer", "strip_suspicious_content"),
        "validate_structured_output": ("app.services.sanitizer", "validate_structured_output"),
        "safe_parse_json": ("app.services.sanitizer", "safe_parse_json"),
        "PrescriptionSchema": ("app.services.sanitizer", "PrescriptionSchema"),
        "AppointmentSchema": ("app.services.sanitizer", "AppointmentSchema"),
        "WeeklyReportSchema": ("app.services.sanitizer", "WeeklyReportSchema"),
        "TemporalMultimodalRetriever": ("app.services.temporal_rag", "TemporalMultimodalRetriever"),
        "temporal_decay": ("app.services.temporal_rag", "temporal_decay"),
        "clinical_significance_from_tags": ("app.services.temporal_rag", "clinical_significance_from_tags"),
        "ALPHA": ("app.services.temporal_rag", "ALPHA"),
        "BETA": ("app.services.temporal_rag", "BETA"),
        "GAMMA": ("app.services.temporal_rag", "GAMMA"),
        "DELTA": ("app.services.temporal_rag", "DELTA"),
        "EPSILON": ("app.services.temporal_rag", "EPSILON"),
        "TAU": ("app.services.temporal_rag", "TAU"),
        "TIER_WEIGHTS": ("app.services.temporal_rag", "TIER_WEIGHTS"),
        "EvaluationHarness": ("app.services.evaluation", "EvaluationHarness"),
        "generate_test_dataset": ("app.services.evaluation", "generate_test_dataset"),
        "compute_recall_at_k": ("app.services.evaluation", "compute_recall_at_k"),
        "compute_future_leak_rate": ("app.services.evaluation", "compute_future_leak_rate"),
        "BM25Baseline": ("app.services.evaluation", "BM25Baseline"),
        "RAGAuditService": ("app.services.rag_audit", "RAGAuditService"),
        "LLMRateLimiter": ("app.services.rag_audit", "LLMRateLimiter"),
        "validate_no_future_leak": ("app.services.rag_audit", "validate_no_future_leak"),
        "ImageRegistrationService": ("app.services.image_registration", "ImageRegistrationService"),
        "image_registration_service": ("app.services.image_registration", "image_registration_service"),
        "ImageSecurityService": ("app.services.image_security", "ImageSecurityService"),
        "PDFSecurityService": ("app.services.pdf_security", "PDFSecurityService"),
        "MedicalFormatter": ("app.services.medical_formatter", "MedicalFormatter"),
        "email_queue": ("app.services.email_queue", "email_queue"),
        "voice_scheduler": ("app.services.voice_scheduler", "voice_scheduler"),
        "validate_notification_prefs": ("app.services.notification_prefs", "validate_notification_prefs"),
        "get_enabled_channels": ("app.services.notification_prefs", "get_enabled_channels"),
        "merge_with_defaults": ("app.services.notification_prefs", "merge_with_defaults"),
        "calendar_security": ("app.services.calendar_security", "calendar_security"),
        "CalendarRateLimiter": ("app.services.calendar_security", "CalendarRateLimiter"),
        "patient_security": ("app.services.patient_security", "patient_security"),
        "PatientSecurityService": ("app.services.patient_security", "PatientSecurityService"),
        "PatientPortalAudit": ("app.services.patient_security", "PatientPortalAudit"),
        "find_available_slots": ("app.services.calendar_service", "find_available_slots"),
        "create_appointment": ("app.services.calendar_service", "create_appointment"),
        "reschedule_appointment": ("app.services.calendar_service", "reschedule_appointment"),
        "cancel_appointment": ("app.services.calendar_service", "cancel_appointment"),
        "query_calendar_nl": ("app.services.calendar_service", "query_calendar_nl"),
        "bulk_reschedule": ("app.services.calendar_service", "bulk_reschedule"),
        "block_doctor_time": ("app.services.calendar_service", "block_doctor_time"),
        "smart_rearrange": ("app.services.calendar_service", "smart_rearrange"),
        "find_optimal_window": ("app.services.calendar_service", "find_optimal_window"),
        "handle_doctor_off": ("app.services.calendar_service", "handle_doctor_off"),
        "WeeklyReportService": ("app.services.weekly_report", "WeeklyReportService"),
        "REPORT_LAYOUTS": ("app.services.weekly_report", "REPORT_LAYOUTS"),
        "build_likert_study": ("app.services.weekly_report", "build_likert_study"),
        "FeatureBEvaluator": ("app.services.feature_b_eval", "FeatureBEvaluator"),
        "generate_100_query_set": ("app.services.feature_b_eval", "generate_100_query_set"),
        "ProjectorTrainer": ("app.services.feature_c_projector", "ProjectorTrainer"),
        "generate_synthetic_pairs": ("app.services.feature_c_projector", "generate_synthetic_pairs"),
        "infonce_loss": ("app.services.feature_c_projector", "infonce_loss"),
        "evaluate_projector": ("app.services.feature_c_eval", "evaluate_projector"),
        "run_qualitative_panel": ("app.services.feature_c_eval", "run_qualitative_panel"),
        "TrajectoryClusterer": ("app.services.feature_e_clustering", "TrajectoryClusterer"),
        "AnomalyDetector": ("app.services.feature_e_clustering", "AnomalyDetector"),
        "run_feature_e_eval": ("app.services.feature_e_clustering", "run_full_evaluation"),
        "export_langfuse_metrics": ("app.services.research_data_mgmt", "export_langfuse_metrics"),
        "verify_data_anonymization": ("app.services.research_data_mgmt", "verify_data_anonymization"),
        "get_research_data_report": ("app.services.research_data_mgmt", "get_research_data_report"),
        "cached_patients": ("app.services.cache", "cached_patients"),
        "cached_doctor_settings": ("app.services.cache", "cached_doctor_settings"),
        "cached_working_hours": ("app.services.cache", "cached_working_hours"),
        "invalidate_cache": ("app.services.cache", "invalidate_cache"),
        "invalidate_patient_cache": ("app.services.cache", "invalidate_patient_cache"),
        "invalidate_doctor_cache": ("app.services.cache", "invalidate_doctor_cache"),
        "safe_get_patient": ("app.services.cache", "safe_get_patient"),
        "gpu_optimizer": ("app.services.gpu_optimizer", "gpu_optimizer"),
        "GPUOptimizer": ("app.services.gpu_optimizer", "GPUOptimizer"),
        "voice_latency_optimizer": ("app.services.gpu_optimizer", "voice_latency_optimizer"),
        "VoiceLatencyOptimizer": ("app.services.gpu_optimizer", "VoiceLatencyOptimizer"),
        "collect_all_metrics": ("app.services.final_eval", "collect_all_metrics"),
        "security_auditor": ("app.services.security_audit", "security_auditor"),
        "SecurityAuditor": ("app.services.security_audit", "SecurityAuditor"),
        "penetration_tester": ("app.services.security_audit", "penetration_tester"),
        "PenetrationTester": ("app.services.security_audit", "PenetrationTester"),
        "run_full_audit": ("app.services.security_audit", "run_full_audit"),
        "check_audit_completeness": ("app.services.audit_log_fixer", "check_audit_completeness"),
        "log_security_event": ("app.services.audit_log_fixer", "log_security_event"),
    }

    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    raise AttributeError(f"module 'app.services' has no attribute '{name}'")


# Eagerly import only non-problematic, frequently-used services
# (these don't trigger the circular chain)
from app.services.redis import redis_service, RedisService  # noqa: F401, E402
