from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttendanceRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    student_id: int
    student_name: str | None = None
    external_student_id: int | None = None
    status: str
    recognition_confidence: float | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    check_in_at: datetime | None
    check_out_at: datetime | None
    late_minutes: int
    detection_count: int


class FrameProcessResponse(BaseModel):
    session_id: int
    faces_detected: int
    students_identified: int
    attendance_updates: int
    identifications: list["IdentificationResult"]


class IdentificationResult(BaseModel):
    student_id: int | None
    external_student_id: int | None
    student_name: str | None
    confidence: float
    is_known: bool


class ExportResponse(BaseModel):
    session_id: int
    export_status: str
    target_url: str
    records_exported: int
    message: str
