from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.modules.attendance.service import AttendanceService
from app.modules.sessions.service import SessionService
from app.schemas.attendance import ExportResponse
from app.schemas.session import SessionReportResponse, SessionResponse, SessionStartRequest
from app.services.export_service import ExportService

router = APIRouter()


@router.post("/start", response_model=SessionResponse)
def start_session(payload: SessionStartRequest, db: Session = Depends(get_db)):
    service = SessionService(db)
    attendance_service = AttendanceService(db)
    session = service.start_session(payload)
    attendance_service.initialize_session_attendance(session.id, session.class_id)
    return SessionResponse.model_validate(session)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = SessionService(db).get_session(session_id)
    return SessionResponse.model_validate(session)


@router.post("/{session_id}/end", response_model=SessionResponse)
def end_session(session_id: int, db: Session = Depends(get_db)):
    session = SessionService(db).end_session(session_id)
    return SessionResponse.model_validate(session)


@router.get("/{session_id}/report", response_model=SessionReportResponse)
def get_session_report(session_id: int, db: Session = Depends(get_db)):
    return SessionService(db).get_report(session_id)


@router.post("/{session_id}/export", response_model=ExportResponse)
def export_session(session_id: int, db: Session = Depends(get_db)):
    return ExportService(db).export_session(session_id)
