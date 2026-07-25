# Pydantic Schemas — Version 2

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ─── User ──────────────────────────────────────
class UserRead(BaseModel):
    id: UUID
    phone: str
    name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Patient ───────────────────────────────────
class PatientBase(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    consent_for_share: bool = False


class PatientCreate(PatientBase):
    pass


class PatientRead(BaseModel):
    id: UUID
    doctor_id: UUID
    user_id: Optional[UUID] = None
    head_version_id: Optional[UUID] = None
    consent_for_share: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Patient Version ──────────────────────────
class PatientVersionBase(BaseModel):
    state_jsonb: Dict[str, Any]
    edit_type: str = Field(..., pattern=r"^(manual|voice|ocr|ai_suggestion|revert)$")
    summary: Optional[str] = Field(None, max_length=500)
    tags: List[str] = Field(default_factory=list)
    clinical_significance: Optional[float] = Field(None, ge=0.0, le=1.0)

    @field_validator("state_jsonb")
    @classmethod
    def state_not_empty(cls, v):
        if not v:
            raise ValueError("state_jsonb must not be empty")
        return v


class PatientVersionCreate(PatientVersionBase):
    pass


class PatientVersionRead(PatientVersionBase):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    parent_version_id: Optional[UUID] = None
    version_number: int = Field(..., ge=1)
    version_hash: str
    author: str
    image_comparison: Optional[Dict[str, Any]] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class PatientVersionDiff(BaseModel):
    added: Dict[str, Any] = {}
    removed: Dict[str, Any] = {}
    modified: Dict[str, Dict[str, Any]] = {}


class PatientVersionTimeline(BaseModel):
    """Lightweight version (no full state_jsonb) for timeline display."""
    id: UUID
    version_number: int
    parent_version_id: Optional[UUID] = None
    author: str
    edit_type: str
    summary: Optional[str] = None
    tags: List[str]
    clinical_significance: float
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Prescription ──────────────────────────────
class MedicationSchema(BaseModel):
    drug: str
    strength: str
    dose: str
    frequency: str
    route: str = "PO"
    duration: str
    instructions: Optional[str] = None
    warnings: List[str] = []


class PrescriptionCreate(BaseModel):
    diagnosis_short: str = Field(..., max_length=120)
    medications: List[MedicationSchema] = []
    investigations: List[str] = []
    lifestyle: List[str] = []
    follow_up_days: int = 30
    follow_up_mode: str = "in-person"
    doctor_notes: Optional[str] = None


class PrescriptionRead(BaseModel):
    id: UUID
    version_id: UUID
    doctor_id: UUID
    rx_jsonb: Dict[str, Any]
    pdf_path: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Invoice ────────────────────────────────────
class InvoiceItem(BaseModel):
    description: str
    qty: int = 1
    rate: int
    amount: int


class InvoiceCreate(BaseModel):
    patient_id: UUID
    appointment_id: Optional[UUID] = None
    items: List[InvoiceItem] = []
    tax: int = 0
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class InvoiceRead(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    invoice_number: str
    items: List[Dict[str, Any]]
    subtotal: int
    tax: int
    total: int
    status: str
    generated_at: datetime
    paid_at: Optional[datetime] = None
    pdf_path: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Certificate ────────────────────────────────
class CertificateCreate(BaseModel):
    patient_id: UUID
    cert_type: str
    cert_jsonb: Dict[str, Any]


class CertificateRead(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    cert_type: str
    cert_jsonb: Dict[str, Any]
    pdf_path: Optional[str] = None
    verification_code: str
    issued_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Appointment ────────────────────────────────
class AppointmentCreate(BaseModel):
    patient_id: UUID
    start_at: datetime
    end_at: datetime
    reason: Optional[str] = None
    source: str = "manual"


class AppointmentRead(BaseModel):
    id: UUID
    doctor_id: UUID
    patient_id: UUID
    start_at: datetime
    end_at: datetime
    reason: Optional[str] = None
    status: str
    source: str
    notified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Health ────────────────────────────────────────
class HealthCheck(BaseModel):
    status: str
    version: str
    services: dict


# ─── Auth ─────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    exp: int
    iat: int
    doctor_id: Optional[UUID] = None
    patient_id: Optional[UUID] = None
    type: str = "access"


# ─── Doctor Settings ──────────────────────────────
class DoctorSettingsUpdate(BaseModel):
    working_hours_json: Optional[Dict[str, List[List[str]]]] = None
    buffer_minutes: Optional[int] = Field(None, ge=0, le=60)
    default_duration: Optional[int] = Field(None, ge=5, le=120)
    auto_email: Optional[bool] = None
    notification_preferences: Optional[Dict[str, Dict[str, Any]]] = None


class DoctorProfileUpdate(BaseModel):
    """Update doctor's profile fields — name, clinic, contact, etc."""
    name: Optional[str] = Field(None, max_length=255)
    speciality: Optional[str] = Field(None, max_length=100)
    clinic_name: Optional[str] = Field(None, max_length=255)
    clinic_address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    registration_number: Optional[str] = Field(None, max_length=100)
    clinic_logo_path: Optional[str] = None

    class Config:
        from_attributes = True


# ─── Doctor Registration & Verification ──────────────
class DoctorRegister(BaseModel):
    """Onboard a new doctor via email/password."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., max_length=255)
    phone: Optional[str] = Field(None, max_length=50)


class DoctorLogin(BaseModel):
    """Login with email and password."""
    email: str
    password: str


class DoctorVerificationSubmit(BaseModel):
    """Submit documents for verification."""
    registration_number: str = Field(..., max_length=100)
    # license_document is handled as a file upload separately


class DoctorProfileRead(BaseModel):
    """Full doctor profile returned to the doctor."""
    id: UUID
    email: str
    name: str
    speciality: Optional[str] = None
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    phone: Optional[str] = None
    registration_number: Optional[str] = None
    verification_status: str = "unverified"
    license_document_path: Optional[str] = None
    rejection_reason: Optional[str] = None
    verified_at: Optional[datetime] = None
    location: Optional[str] = None
    settings: dict = {}
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VerificationPending(BaseModel):
    """A doctor pending verification review (admin view)."""
    id: UUID
    email: str
    name: str
    speciality: Optional[str] = None
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    phone: Optional[str] = None
    registration_number: Optional[str] = None
    license_document_path: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VerificationAction(BaseModel):
    """Admin action on a verification request."""
    doctor_id: UUID
    reason: Optional[str] = Field(None, max_length=500, description="Rejection reason")