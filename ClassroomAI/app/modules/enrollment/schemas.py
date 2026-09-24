from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EnrollmentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class EnrollmentStats(BaseModel):
    accepted: int = 0
    rejected_blurry: int = 0
    rejected_too_small: int = 0
    rejected_no_face: int = 0
    rejected_duplicate: int = 0


class EnrollmentStatusResponse(BaseModel):
    student_id: int
    status: EnrollmentStatus
    samples_captured: int = Field(ge=0)
    samples_needed: int = Field(ge=1)
    message: str = ""
    stats: EnrollmentStats = Field(default_factory=EnrollmentStats)

    model_config = {"from_attributes": True}


class EnrollmentStartResponse(EnrollmentStatusResponse):
    pass


class EnrollmentStopResponse(EnrollmentStatusResponse):
    pass


class PhotoEnrollmentResponse(BaseModel):
    success: bool
    student_id: int
    face_detected: bool
    embedding_saved: bool
    photo_path: str | None = None
