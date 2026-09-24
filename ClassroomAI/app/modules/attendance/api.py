from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.frame_processor import FrameProcessor
from app.api.deps import get_db
from app.core.enums import SessionStatus
from app.modules.attendance.schemas import AttendanceRecordResponse, FrameProcessResponse
from app.modules.attendance.service import AttendanceService
from app.modules.sessions.service import SessionService
from app.core.enums import AttendanceStatus
from app.core.school_clock import school_now, school_today
from app.models.attendance import AttendanceRecord
from app.models.session import ClassSession
from app.models.student import Student

router = APIRouter()


class ManualAttendanceUpdate(BaseModel):
    present: bool


def _daily_session(db: Session, class_id: int) -> ClassSession:
    session = (
        db.query(ClassSession)
        .filter(
            ClassSession.class_id == class_id,
            ClassSession.attendance_date == school_today(),
        )
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No attendance has been started for this classroom today",
        )
    return session


@router.get("/daily/class/{class_id}")
def get_daily_attendance(class_id: int, db: Session = Depends(get_db)):
    """Return the persisted attendance for this class on the Riyadh school day."""
    session = _daily_session(db, class_id)
    records = AttendanceService(db).list_session_attendance(session.id)
    return {
        "session_id": session.id,
        "attendance_date": session.attendance_date,
        "roll_call_started_at": session.started_at,
        "roll_call_completed_at": session.initial_roll_call_completed_at,
        "records": [record.model_dump(mode="json") for record in records],
    }


@router.patch("/daily/class/{class_id}/students/{external_student_id}")
def update_daily_attendance(
    class_id: int,
    external_student_id: int,
    payload: ManualAttendanceUpdate,
    db: Session = Depends(get_db),
):
    """Manually correct today's attendance without replacing the daily record."""
    session = _daily_session(db, class_id)
    student = (
        db.query(Student)
        .filter(
            Student.class_id == class_id,
            Student.external_student_id == external_student_id,
            Student.is_active.is_(True),
        )
        .first()
    )
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == session.id, AttendanceRecord.student_id == student.id)
        .first()
    )
    if record is None:
        record = AttendanceRecord(session_id=session.id, student_id=student.id)
        db.add(record)

    if payload.present:
        arrived_late = session.initial_roll_call_completed_at is not None
        record.status = AttendanceStatus.LATE.value if arrived_late else AttendanceStatus.PRESENT.value
        record.check_in_at = school_now()
        if arrived_late:
            record.late_minutes = max(0, int((record.check_in_at - session.started_at).total_seconds() // 60))
    else:
        record.status = AttendanceStatus.ABSENT.value
        record.check_in_at = None
        record.late_minutes = 0
    db.commit()

    result = AttendanceService(db).list_session_attendance(session.id)
    return next(item.model_dump(mode="json") for item in result if item.student_id == student.id)


@router.get("/session/{session_id}", response_model=list[AttendanceRecordResponse])
def get_session_attendance(session_id: int, db: Session = Depends(get_db)):
    SessionService(db).get_session(session_id)
    return AttendanceService(db).list_session_attendance(session_id)


@router.post("/session/{session_id}/process-frame", response_model=FrameProcessResponse)
async def process_session_frame(
    session_id: int,
    frame: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    session = SessionService(db).get_session(session_id)
    if session.status != SessionStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot process frames for an inactive session",
        )

    image_bytes = await frame.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty frame uploaded",
        )

    try:
        return FrameProcessor(db).process_frame(session, image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
