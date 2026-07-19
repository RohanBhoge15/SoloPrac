# SoloPrac Backend Schemas

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing_extensions import Annotated


# Base schemas
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# Doctor schemas
class DoctorBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    speciality: str = Field(default="General Practice", max_length=100)
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    phone: Optional[str] = None
    registration_number: Optional[str] = None


class DoctorCreate(DoctorBase):
    email: EmailStr


class DoctorRead(DoctorBase):
    id: uuid.UUID
    email: EmailStr
    created_at: datetime


# Patient schemas
class PatientBase(BaseSchema):
    pass


class PatientCreate(BaseSchema):
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class PatientRead(BaseSchema):
    id: uuid.UUID
    doctor_id: uuid.UUID
    head_version_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class PatientWithVersion(PatientRead):
    head_version: Optional[PatientVersionRead] = None


# Patient Version schemas
class PatientVersionBase(BaseSchema):
    state_jsonb: dict
    version_hash: str
    author: str = Field(..., pattern=r"^(doctor|agent):.+")
    edit_type: str = Field(..., pattern=r"^(manual|voice|ocr|ai_suggestion|revert)$")
    summary: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    clinical_significance: Optional[float] = None
    image_comparison: Optional[dict] = None


class PatientVersionCreate(PatientVersionBase):
    patient_id: uuid.UUID
    parent_version_id: Optional[uuid.UUID] = None


class PatientVersionRead(PatientVersionBase):
    id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    parent_version_id: Optional[uuid.UUID] = None
    version_number: int
    timestamp: datetime


class PatientVersionDiff(BaseSchema):
    added: dict
    removed: dict
    modified: dict


# Auth schemas
class Token(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseSchema):
    sub: str
    exp: int
    type: str  # "access" | "refresh"


# Health check
class HealthCheck(BaseSchema):
    status: str
    version: str
    services: dict[str, str]


# Error response
class ErrorResponse(BaseSchema):
    detail: str
    error_code: Optional[str] = None