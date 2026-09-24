from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


@dataclass(slots=True)
class FaceHit:
    """Result for a single detected face in one recognition frame."""

    face_location: tuple[int, int, int, int]  # (top, right, bottom, left)
    matched: bool
    student_id: int | None
    external_student_id: int | None
    student_name: str | None
    confidence: float  # 0.0 – 1.0


class PipelineStatus(str, Enum):
    IDLE     = "idle"
    RUNNING  = "running"
    STOPPING = "stopping"
    STOPPED  = "stopped"
    FAILED   = "failed"


class RecognitionStatusResponse(BaseModel):
    status: PipelineStatus
    frames_processed: int = 0
    last_error: str | None = None
