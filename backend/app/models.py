# SQLAlchemy Models — Versioned Patient Records

import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Integer, Float, Boolean,
    BigInteger, Index, UniqueConstraint, event,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, BYTEA, INET, ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship, declared_attr
from sqlalchemy import text
from geoalchemy2 import Geography
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    """Cross-tenant app user — no doctor scope, no RLS.

    A user authenticates via email/password. They can be a patient at
    multiple clinics; each visit creates a separate Patient row
    scoped to that doctor.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    phone_hash = Column(String(64), unique=True, nullable=False, index=True)
    dob = Column(DateTime(timezone=True), nullable=True)
    gender = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    # Medical profile (filled at first login)
    blood_group = Column(String(5), nullable=True)
    allergies = Column(Text, nullable=True)
    known_conditions = Column(Text, nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    insurance_info = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # No RLS — this table is intentionally cross-tenant

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    speciality = Column(String(100), default="General Practice")
    location = Column(Geography(geometry_type="POINT", srid=4326), nullable=True)  # PostGIS geography point
    clinic_name = Column(String(255), nullable=False, default="")
    clinic_address = Column(Text, nullable=False, default="")
    pincode = Column(String(6), nullable=True, index=True)  # Indian 6-digit PIN code
    phone = Column(String(50), nullable=False, default="")
    registration_number = Column(String(100), nullable=True)
    password_hash = Column(String(255), nullable=True)
    verification_status = Column(
        String(20), nullable=False, default="unverified",
        comment="unverified | pending_verification | verified | rejected"
    )
    license_document_path = Column(String(500), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    # ABDM verification fields
    state_medical_council = Column(String(255), nullable=True)
    year_of_registration = Column(Integer, nullable=True)
    qualification = Column(String(255), nullable=True)  # populated from ABDM
    abdm_verified_at = Column(DateTime(timezone=True), nullable=True)
    photo_url = Column(String(500), nullable=True)  # profile photo S3/MinIO path
    settings = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    patients = relationship("Patient", back_populates="doctor")
    versions = relationship("PatientVersion", back_populates="doctor")
    prescriptions = relationship("PrescriptionBox", back_populates="doctor")
    invoices = relationship("Invoice", back_populates="doctor")
    certificates = relationship("Certificate", back_populates="doctor")
    appointments = relationship("Appointment", back_populates="doctor")
    audit_logs = relationship("AuditLog", back_populates="doctor")
    sessions = relationship("DoctorSession", back_populates="doctor")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    head_version_id = Column(UUID(as_uuid=True), ForeignKey("patient_versions.id"), nullable=True)
    phone_enc = Column(BYTEA)
    email_enc = Column(BYTEA)
    consent_for_share = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    doctor = relationship("Doctor", back_populates="patients")
    user = relationship("User")
    versions = relationship(
        "PatientVersion",
        back_populates="patient",
        foreign_keys="PatientVersion.patient_id",
        order_by="PatientVersion.version_number.desc()",
        lazy="selectin",
    )
    head_version = relationship(
        "PatientVersion",
        foreign_keys=[head_version_id],
        post_update=True,
        uselist=False,
    )
    prescriptions = relationship("PrescriptionBox", back_populates="patient")
    invoices = relationship("Invoice", back_populates="patient")
    certificates = relationship("Certificate", back_populates="patient")
    appointments = relationship("Appointment", back_populates="patient")
    time_preferences = relationship("PatientTimePreference", back_populates="patient")
    risk_alerts = relationship("RiskAlert", back_populates="patient")
    consent_records = relationship("ConsentRecord", back_populates="patient")
    notifications = relationship("PatientNotification", back_populates="patient")


EDIT_TYPE_CHOICES = {"manual", "voice", "ocr", "ai_suggestion", "revert"}


class PatientVersion(Base):
    """
    Immutable version chain for patient records.

    Every write to a patient appends a new version. The chain is linked
    via parent_version_id, forming a Git-like DAG. State is content-addressed
    via version_hash = sha256(canonical_json(state_jsonb)).
    """
    __tablename__ = "patient_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_version_id = Column(UUID(as_uuid=True), ForeignKey("patient_versions.id"), nullable=True)
    version_number = Column(Integer, nullable=False)
    state_jsonb = Column(JSONB, nullable=False)
    version_hash = Column(String(64), nullable=False)
    author = Column(String(100), nullable=False)  # 'doctor:<uuid>' | 'agent:<name>'
    edit_type = Column(String(20), nullable=False)  # manual|voice|ocr|ai_suggestion|revert
    summary = Column(Text, nullable=True)
    tags = Column(PG_ARRAY(String), default=list)
    clinical_significance = Column(Float, default=0.0)
    image_comparison = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    patient = relationship("Patient", back_populates="versions", foreign_keys=[patient_id])
    doctor = relationship("Doctor", back_populates="versions")
    parent_version = relationship("PatientVersion", remote_side=[id], uselist=False)

    __table_args__ = (
        UniqueConstraint("patient_id", "version_number", name="uq_patient_version_number"),
        Index("ix_patient_versions_patient_ts", "patient_id", "timestamp"),
        Index("ix_patient_versions_doctor_ts", "doctor_id", "timestamp"),
    )

    @staticmethod
    def compute_hash(state: dict) -> str:
        """Content-addressed hash: SHA256 of canonical (sorted, compact) JSON."""
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify_hash(self) -> bool:
        """Verify that stored state matches the version hash (tamper check)."""
        return self.version_hash == self.compute_hash(self.state_jsonb)

    def __repr__(self):
        return f"<PatientVersion(patient={self.patient_id}, v{self.version_number}, {self.edit_type})>"


# ── Audit event: validate edit_type on insert ──
@event.listens_for(PatientVersion, "before_insert")
def validate_patient_version(mapper, connection, target):
    if target.edit_type not in EDIT_TYPE_CHOICES:
        raise ValueError(f"Invalid edit_type: {target.edit_type}. Must be one of {EDIT_TYPE_CHOICES}")
    if not target.author or ":" not in target.author:
        raise ValueError(f"Invalid author format: {target.author}. Must be 'doctor:<id>' or 'agent:<name>'")
    if target.parent_version_id and target.parent_version_id == target.id:
        raise ValueError("A version cannot be its own parent")
    if target.version_number < 1:
        raise ValueError("version_number must be >= 1")


# ── Prescription Boxes ──
class PrescriptionBox(Base):
    __tablename__ = "prescription_boxes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("patient_versions.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    rx_jsonb = Column(JSONB, nullable=False)
    pdf_path = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=utc_now)

    version = relationship("PatientVersion")
    doctor = relationship("Doctor", back_populates="prescriptions")
    patient = relationship("Patient", back_populates="prescriptions")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)
    invoice_number = Column(String(50), unique=True, nullable=False)
    items = Column(JSONB, nullable=False)
    subtotal = Column(Integer, nullable=False)
    tax = Column(Integer, default=0)
    total = Column(Integer, nullable=False)
    status = Column(String(20), default="pending")
    payment_method = Column(String(20))
    notes = Column(Text)
    generated_at = Column(DateTime(timezone=True), default=utc_now)
    paid_at = Column(DateTime(timezone=True))
    pdf_path = Column(String(500))

    doctor = relationship("Doctor", back_populates="invoices")
    patient = relationship("Patient", back_populates="invoices")
    appointment = relationship("Appointment", back_populates="invoice")


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    cert_type = Column(String(50), nullable=False)
    cert_jsonb = Column(JSONB, nullable=False)
    pdf_path = Column(String(500))
    verification_code = Column(String(100), unique=True)
    issued_at = Column(DateTime(timezone=True), default=utc_now)

    doctor = relationship("Doctor", back_populates="certificates")
    patient = relationship("Patient", back_populates="certificates")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    reason = Column(Text)
    status = Column(String(20), default="scheduled")
    source = Column(String(20), default="manual")
    notified = Column(Boolean, default=False)
    telemedicine_consent = Column(Boolean, default=False)
    telemedicine_consent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    doctor = relationship("Doctor", back_populates="appointments")
    patient = relationship("Patient", back_populates="appointments")
    invoice = relationship("Invoice", back_populates="appointment", uselist=False)

    __table_args__ = (
        Index("ix_appointments_doctor_start", "doctor_id", "start_at"),
        Index("ix_appointments_patient_start", "patient_id", "start_at"),
    )


class PatientTimePreference(Base):
    __tablename__ = "patient_time_preferences"

    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    weekday = Column(Integer, primary_key=True)
    hour_bucket = Column(Integer, primary_key=True)
    count = Column(Integer, default=0)
    last_seen = Column(DateTime(timezone=True))

    patient = relationship("Patient", back_populates="time_preferences")


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(50), nullable=False)
    reason = Column(Text, nullable=False)
    severity = Column(Float, nullable=False)
    triggered_at = Column(DateTime(timezone=True), default=utc_now)
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey("doctors.id"))
    acknowledged_at = Column(DateTime(timezone=True))

    patient = relationship("Patient", back_populates="risk_alerts")


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    consent_type = Column(String(50), nullable=False)
    granted = Column(Boolean, nullable=False, default=False)
    purpose = Column(Text, nullable=True)
    granted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    patient = relationship("Patient", back_populates="consent_records")


class DoctorSession(Base):
    __tablename__ = "doctor_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    token_jti = Column(String(64), unique=True, nullable=False, index=True)
    device_info = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    last_active_at = Column(DateTime(timezone=True), default=utc_now)
    revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    doctor = relationship("Doctor", back_populates="sessions")


class PatientNotification(Base):
    __tablename__ = "patient_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(50), nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    channel = Column(PG_ARRAY(String), default=list)
    meta = Column(JSONB, nullable=True)  # resource linkage: {resource_type, resource_id, pdf_url, ...}
    read = Column(Boolean, default=False)
    delivered_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utc_now)

    patient = relationship("Patient", back_populates="notifications")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    actor = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(UUID(as_uuid=True))
    payload_jsonb = Column(JSONB)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    doctor = relationship("Doctor", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_log_doctor_occurred", "doctor_id", "occurred_at"),
    )


class ReportVerification(Base):
    __tablename__ = "report_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    verification_code = Column(String(100), unique=True, nullable=False, index=True)
    report_type = Column(String(20), nullable=False, default="weekly_report")
    generated_at = Column(DateTime(timezone=True), default=utc_now)
    verified_at = Column(DateTime(timezone=True), nullable=True)


class ImageComparison(Base):
    __tablename__ = "image_comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(UUID(as_uuid=True), ForeignKey("patient_versions.id", ondelete="CASCADE"), nullable=False)
    current_image_path = Column(String(500), nullable=False)
    matched_version_id = Column(UUID(as_uuid=True), ForeignKey("patient_versions.id"), nullable=True)
    matched_image_path = Column(String(500))
    area_change_pct = Column(Float)
    edge_convergence_score = Column(Float)
    color_histogram_shift = Column(Float)
    overlay_path = Column(String(500))
    clinical_summary = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    doctor = relationship("Doctor")
    version = relationship("PatientVersion", foreign_keys=[version_id])
    matched_version = relationship("PatientVersion", foreign_keys=[matched_version_id])