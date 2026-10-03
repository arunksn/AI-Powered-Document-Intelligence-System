from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""


class SignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str



class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    filename: str
    source_format: Optional[str]
    is_scanned: bool
    ocr_confidence: Optional[float]
    low_quality_flag: bool
    status: str
    current_stage: int
    error_message: Optional[str]
    document_type: Optional[str]
    primary_parties: Any
    key_dates: Any
    governing_jurisdiction: Optional[str]
    extracted_entities: Any
    risk_score: Optional[float]
    risk_breakdown: Any
    created_at: datetime
    updated_at: datetime


class AnomalyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    severity: str
    category: str
    explanation: str
    evidence: Any


class ContradictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_a_id: str
    document_b_id: str
    field: str
    value_a: str
    value_b: str
    explanation: str


class CrmSyncOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider: str
    external_record_id: Optional[str]
    status: str
    last_error: Optional[str]
    last_synced_at: Optional[datetime]
