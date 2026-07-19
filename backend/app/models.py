# SQLAlchemy Models

import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Integer, Float, Boolean,
    BigInteger, Index, func, JSON, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, BYTEA, INET, ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship, declarative_base
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    speciality = Column(String(100), default="General Practice")
    location = Column(String(500))  # Store as text, parse lat/lng on read
    clinic_name = Column(String(255))
    clinic_address = Column(Text)
    phone = Column(String(50))
    registration_number = Column(String(100))
    settings = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), default=utc_now)

    # Relationships
    patients = relationship("Patient", back_populates="doctor")
    versions = relationship("PatientVersion", back_populates="doctor")
    prescriptions = relationship("PrescriptionBox", back_populates="doctor")
    invoices = relationship("Invoice", back_populates="doctor")
    certificates = relationship("Certificate", back_populates="doctor")
    appointments = relationship("Appointment", back_populates="doctor")
    audit_logs = relationship("AuditLog", back_populates="doctor")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    head_version_id = Column(UUID(as_uuid=True), ForeignKey("patient_versions.id"))
    phone_enc = Column(BYTEA)
    email_enc = Column(BYTEA)
    consent_for_share = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    doctor = relationship("Doctor", back_populates="patients")
    versions = relationship("PatientVersion", back_populates="patient", foreign_keys="PatientVersion.patient_id")
    head_version = relationship("PatientVersion", foreign_keys=[head_version_id])
    prescriptions = relationship("PrescriptionBox", back_populates="patient")
    invoices = relationship("Invoice", back_populates="patient")
    certificates = relationship("Certificate", back_populates="patient")
    appointments = relationship("Appointment", back_populates="patient")
    time_preferences = relationship("PatientTimePreference", back_populates="patient")
    risk_alerts = relationship("RiskAlert", back_populates="patient")
    notifications = relationship("PatientNotification", back_populates="patient")


class PatientVersion(Base):
    __tablename__ = "patient_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_version_id = Column(UUID(as_uuid=True), ForeignKey("patient_versions.id"), nullable=True)
    version_number = Column(Integer, nullable=False)
    state_jsonb = Column(JSONB, nullable=False)
    version_hash = Column(String(64), nullable=False)
    author = Column(String(100), nullable=False)
    edit_type = Column(String(20), nullable=False)  # manual|voice|ocr|ai_suggestion|revert
    summary = Column(Text)
    tags = Column(PG_ARRAY(String), default=[])
    clinical_significance = Column(Float, default=0.0)
    image_comparison = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="versions")
    doctor = relationship("Doctor", back_populates="versions")
    parent_version = relationship("PatientVersion", remote_side=[id])
    prescriptions = relationship("PrescriptionBox", back_populates="version")
    image_comparisons = relationship("ImageComparison", back_populates="version")

    __table_args__ = (
        Index("ix_patient_versions_patient_timestamp", "patient_id", "timestamp", postgresql_using="btree"),
        Index("ix_patient_versions_doctor_timestamp", "doctor_id", "timestamp", postgresql_using="btree"),
        # Unique constraint on patient_id + version_number
        # Note: We don't add it here to allow application-level control
    )

    @staticmethod
    def compute_hash(state: dict) -> str:
        """Compute SHA256 of canonical JSON representation."""
        canonical = json.dumps(state, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()


class PrescriptionBox(Base):
    __tablename__ = "prescription_boxes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("patient_versions.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    rx_jsonb = Column(JSONB, nullable=False)
    pdf_path = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=utc_now)

    version = relationship("PatientVersion", back_populates="prescriptions")
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
    subtotal = Column(Integer, nullable=False)  # Stored in paise/cents
    tax = Column(Integer, default=0)
    total = Column(Integer, nullable=False)
    status = Column(String(20), default="pending")  # pending|paid|cancelled
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
    cert_type = Column(String(50), nullable=False)  # sick_leave|fitness|school|disability|other
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
    status = Column(String(20), default="scheduled")  # scheduled|done|cancelled|moved
    source = Column(String(20), default="manual")  # manual|voice|agent|patient_portal
    notified = Column(Boolean, default=False)
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
    weekday = Column(Integer, primary_key=True)  # 0-6
    hour_bucket = Column(Integer, primary_key=True)  # 0-23
    count = Column(Integer, default=0)
    last_seen = Column(DateTime(timezone=True))

    patient = relationship("Patient", back_populates="time_preferences")


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(50), nullable=False)  # trajectory_drift|anomaly
    reason = Column(Text, nullable=False)
    severity = Column(Float, nullable=False)  # 0-1
    triggered_at = Column(DateTime(timezone=True), default=utc_now)
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey("doctors.id"))
    acknowledged_at = Column(DateTime(timezone=True))

    doctor = relationship("Doctor", back_populates="risk_alerts", foreign_keys=[doctor_id])
    patient = relationship("Patient", back_populates="risk_alerts")
    acknowledged_by_doctor = relationship("Doctor", foreign_keys=[acknowledged_by])


class PatientNotification(Base):
    __tablename__ = "patient_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(50), nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    channel = Column(PG_ARRAY(String), default=["in_app"])
    read = Column(Boolean, default=False)
    delivered_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utc_now)

    patient = relationship("Patient", back_populates="notifications")
    doctor = relationship("Doctor", back_populates="notifications")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"))
    actor = Column(String(100), nullable=False)  # doctor:<id> | patient:<id> | agent:<name> | system
    action = Column(String(50), nullable=False)  # read|write|ai_suggest|approve|export|book|cancel
    resource_type = Column(String(50), nullable=False)  # patient|version|appointment|rx|invoice|certificate|report
    resource_id = Column(UUID(as_uuid=True))
    payload_jsonb = Column(JSONB)
    ip_address = Column(INET)
    user_agent = Column(Text)
    occurred_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    doctor = relationship("Doctor", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_log_doctor_occurred", "doctor_id", "occurred_at"),
    )


class ImageComparison(Base):
    __tablename__ = "image_comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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

    version = relationship("PatientVersion", back_populates="image_comparisons", foreign_keys=[version_id])
    matched_version = relationship("PatientVersion", foreign_keys=[matched_version_id])