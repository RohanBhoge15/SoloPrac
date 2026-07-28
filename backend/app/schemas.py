# Pydantic Schemas — Version 2

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ─── User ──────────────────────────────────────
class UserRegister(BaseModel):
    """Patient registration — all compulsory fields."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., max_length=255)
    phone: str = Field(..., max_length=20)
    dob: str = Field(..., description="Date of birth YYYY-MM-DD")
    gender: str = Field(..., pattern=r"^(male|female|other)$")
    address: str = Field(..., min_length=1)


class UserLogin(BaseModel):
    """Patient login with email and password."""
    email: str
    password: str


class UserUpdate(BaseModel):
    """Update user profile fields."""
    name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    dob: Optional[str] = None
    gender: Optional[str] = Field(None, pattern=r"^(male|female|other)$")
    address: Optional[str] = None
    blood_group: Optional[str] = Field(None, pattern=r"^(A\+|A-|B\+|B-|AB\+|AB-|O\+|O-)$")
    allergies: Optional[str] = None
    known_conditions: Optional[str] = None
    height_cm: Optional[float] = Field(None, ge=0, le=300)
    weight_kg: Optional[float] = Field(None, ge=0, le=500)
    emergency_contact_name: Optional[str] = Field(None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    insurance_info: Optional[str] = None


class UserRead(BaseModel):
    id: UUID
    email: str
    name: str
    phone: str
    dob: Optional[datetime] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    known_conditions: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    insurance_info: Optional[str] = None
    created_at: datetime
    profile_complete: bool = False

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
    min_consultation_fee: Optional[int] = Field(None, ge=0)
    clinic_phone: Optional[str] = Field(None, max_length=50)
    clinic_email: Optional[str] = Field(None, max_length=255)
    upi_id: Optional[str] = Field(None, max_length=100)


class DoctorProfileUpdate(BaseModel):
    """Update doctor's profile fields — name, clinic, contact, location, etc."""
    name: Optional[str] = Field(None, max_length=255)
    speciality: Optional[str] = Field(None, max_length=100)
    clinic_name: Optional[str] = Field(None, max_length=255)
    clinic_address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    registration_number: Optional[str] = Field(None, max_length=100)
    photo_url: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    pincode: Optional[str] = Field(None, min_length=6, max_length=6)


# ─── Patient Field Update ─────────────────────────
class DemographicsPatch(BaseModel):
    """Allowed demographics fields for inline edit."""
    name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    dob: Optional[str] = None  # YYYY-MM-DD
    gender: Optional[str] = Field(None, pattern=r"^(male|female|other)$")
    address: Optional[str] = None
    blood_group: Optional[str] = Field(None, pattern=r"^(A\+|A-|B\+|B-|AB\+|AB-|O\+|O-)$")
    allergies: Optional[str] = None
    known_conditions: Optional[str] = None
    height_cm: Optional[float] = Field(None, ge=0, le=300)
    weight_kg: Optional[float] = Field(None, ge=0, le=500)
    emergency_contact_name: Optional[str] = Field(None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    insurance_info: Optional[str] = None


class PatientFieldUpdate(BaseModel):
    """Validated patch for patient fields — only allows known top-level sections."""
    demographics: Optional[DemographicsPatch] = None
    # Add other sections as needed:
    # vitals: Optional[Dict] = None
    # medications: Optional[List] = None

    class Config:
        from_attributes = True


# ─── Doctor Registration & Verification ──────────────
class DoctorRegister(BaseModel):
    """Onboard a new doctor via email/password."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., max_length=255)
    phone: str = Field(..., max_length=50)
    clinic_name: str = Field(..., min_length=1, max_length=255)
    clinic_address: str = Field(..., min_length=1)
    speciality: Optional[str] = Field(None, max_length=100)


class DoctorLogin(BaseModel):
    """Login with email and password."""
    email: str
    password: str


class DoctorVerificationSubmit(BaseModel):
    """Submit ABDM details for verification."""
    registration_number: str = Field(..., max_length=100)
    state_medical_council: str = Field(..., max_length=255)
    year_of_registration: int = Field(..., ge=1900, le=2030)


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
    state_medical_council: Optional[str] = None
    year_of_registration: Optional[int] = None
    years_experience: Optional[int] = None  # computed from year_of_registration
    qualification: Optional[str] = None
    verification_status: str = "unverified"
    photo_url: Optional[str] = None
    license_document_path: Optional[str] = None
    rejection_reason: Optional[str] = None
    verified_at: Optional[datetime] = None
    abdm_verified_at: Optional[datetime] = None
    location: Optional[str] = None
    settings: dict = {}
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm(cls, obj):
        data = super().from_orm(obj)
        if obj.year_of_registration:
            from datetime import date
            data.years_experience = date.today().year - obj.year_of_registration
        return data


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