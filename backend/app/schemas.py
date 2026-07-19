# Pydantic Schemas

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# Patient Schemas
class PatientBase(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    consent_for_share: bool = False


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    consent_for_share: Optional[bool] = None


class PatientRead(PatientBase):
    id: UUID
    doctor_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Patient Version Schemas
class PatientVersionBase(BaseModel):
    version_number: int
    edit_type: str
    summary: Optional[str] = None
    tags: List[str] = []
    clinical_significance: float = 0.0


class PatientVersionRead(PatientVersionBase):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    parent_version_id: Optional[UUID] = None
    state_jsonb: Dict[str, Any]
    version_hash: str
    author: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class PatientVersionTimeline(PatientVersionBase):
    """Lightweight version for timeline display."""
    id: UUID
    version_number: int
    author: str
    edit_type: str
    summary: Optional[str] = None
    tags: List[str]
    clinical_significance: float
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class PatientVersionDiff(BaseModel):
    added: Dict[str, Any] = {}
    removed: Dict[str, Any] = {}
    modified: Dict[str, Dict[str, Any]] = {}


# Prescription Schemas
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


# Invoice Schemas
class InvoiceItem(BaseModel):
    description: str
    qty: int = 1
    rate: int  # in paise/cents
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
    appointment_id: Optional[UUID] = None
    invoice_number: str
    items: List[Dict[str, Any]]
    subtotal: int
    tax: int
    total: int
    status: str
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    generated_at: datetime
    paid_at: Optional[datetime] = None
    pdf_path: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Certificate Schemas
class CertificateCreate(BaseModel):
    patient_id: UUID
    cert_type: str  # sick_leave|fitness|school|disability|other
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


# Appointment Schemas
class AppointmentBase(BaseModel):
    patient_id: UUID
    start_at: datetime
    end_at: datetime
    reason: Optional[str] = None
    source: str = "manual"


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentRead(AppointmentBase):
    id: UUID
    doctor_id: UUID
    status: str
    notified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Notification Schemas
class NotificationCreate(BaseModel):
    patient_id: UUID
    kind: str
    subject: str
    body: str
    channel: List[str] = ["in_app"]


class NotificationRead(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    kind: str
    subject: str
    body: str
    channel: List[str]
    read: bool
    delivered_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Auth Schemas
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: str
    exp: int
    iat: int
    doctor_id: Optional[UUID] = None
    patient_id: Optional[UUID] = None


# Doctor Settings
class DoctorSettings(BaseModel):
    working_hours_json: Dict[str, List[List[str]]] = {}
    buffer_minutes_between_consults: int = 5
    default_consult_duration: int = 20
    auto_email_on_change: bool = True
    patient_preference_decay_days: int = 180
    notification_preferences: Dict[str, Any] = {}
    certificate_templates: Dict[str, Any] = {}


class DoctorSettingsUpdate(BaseModel):
    working_hours_json: Optional[Dict[str, List[List[str]]]] = None
    buffer_minutes_between_consults: Optional[int] = None
    default_consult_duration: Optional[int] = None
    auto_email_on_change: Optional[bool] = None
    patient_preference_decay_days: Optional[int] = None
    notification_preferences: Optional[Dict[str, Any]] = None
    certificate_templates: Optional[Dict[str, Any]] = None