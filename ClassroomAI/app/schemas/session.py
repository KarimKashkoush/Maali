from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionStartRequest(BaseModel):
    class_id: int
    external_session_id: int | None = None
    room_id: int | None = None
    teacher_id: int | None = None
    subject_id: int | None = None
    branch_id: int | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_session_id: int | None
    class_id: int
    room_id: int | None
    teacher_id: int | None
    subject_id: int | None
    branch_id: int | None
    attendance_date: date | None
    initial_roll_call_completed_at: datetime | None
    status: str
    started_at: datetime
    ended_at: datetime | None


class SessionReportResponse(BaseModel):
    session: SessionResponse
    total_students: int
    present_count: int
    late_count: int
    absent_count: int
    left_count: int
    average_confidence: float | None
