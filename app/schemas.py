from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RecipientIn(BaseModel):
    """Validates ONE recipient. Used per row, not on the whole request."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    achievement: str = Field(default="Participation", min_length=1, max_length=200)


class JobCreate(BaseModel):
    """Validates the REQUEST as a whole."""
    event_name: str = Field(min_length=1, max_length=200)
    issued_by: str = Field(min_length=1, max_length=200)
    recipients: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class JobCreated(BaseModel):
    job_id: str
    status: str
    total: int
    accepted: int
    rejected: int


class CertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    row_index: int
    recipient_name: str | None
    recipient_email: str | None
    status: str
    error: str | None


class JobStatusOut(BaseModel):
    job_id: str
    event_name: str
    status: str
    created_at: datetime
    total: int
    generated: int
    failed: int
    invalid: int
    pending: int
    certificates: list[CertificateOut]