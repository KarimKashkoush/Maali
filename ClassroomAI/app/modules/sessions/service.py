from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.enums import AttendanceStatus, SessionStatus
from app.models.session import ClassSession
from app.schemas.session import SessionReportResponse, SessionResponse, SessionStartRequest


class SessionService:
    def __init__(self, db: Session):
        self.db = db

    def start_session(self, payload: SessionStartRequest) -> ClassSession:
        active = (
            self.db.query(ClassSession)
            .filter(
                ClassSession.class_id == payload.class_id,
                ClassSession.status == SessionStatus.ACTIVE.value,
            )
            .first()
        )
        if active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Active session already exists for class {payload.class_id}",
            )

        if payload.external_session_id is not None:
            existing = (
                self.db.query(ClassSession)
                .filter(ClassSession.external_session_id == payload.external_session_id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Session with this external_session_id already exists",
                )

        session = ClassSession(
            external_session_id=payload.external_session_id,
            class_id=payload.class_id,
            room_id=payload.room_id,
            teacher_id=payload.teacher_id,
            subject_id=payload.subject_id,
            branch_id=payload.branch_id,
            status=SessionStatus.ACTIVE.value,
            started_at=datetime.utcnow(),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: int) -> ClassSession:
        session = self.db.query(ClassSession).filter(ClassSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session

    def end_session(self, session_id: int) -> ClassSession:
        session = self.get_session(session_id)
        if session.status == SessionStatus.ENDED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session is already ended",
            )

        session.status = SessionStatus.ENDED.value
        session.ended_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_report(self, session_id: int) -> SessionReportResponse:
        from app.models.attendance import AttendanceRecord
        from app.models.student import Student

        session = self.get_session(session_id)
        records = (
            self.db.query(AttendanceRecord)
            .filter(AttendanceRecord.session_id == session_id)
            .all()
        )

        total_students = (
            self.db.query(Student)
            .filter(Student.class_id == session.class_id, Student.is_active.is_(True))
            .count()
        )

        present_count = sum(
            1
            for r in records
            if r.status in {AttendanceStatus.PRESENT.value, AttendanceStatus.RETURNED.value}
        )
        late_count = sum(1 for r in records if r.status == AttendanceStatus.LATE.value)
        left_count = sum(1 for r in records if r.status == AttendanceStatus.LEFT.value)
        absent_count = sum(1 for r in records if r.status == AttendanceStatus.ABSENT.value)

        confidences = [r.recognition_confidence for r in records if r.recognition_confidence]
        average_confidence = (
            round(sum(confidences) / len(confidences), 4) if confidences else None
        )

        return SessionReportResponse(
            session=SessionResponse.model_validate(session),
            total_students=total_students,
            present_count=present_count,
            late_count=late_count,
            absent_count=absent_count,
            left_count=left_count,
            average_confidence=average_confidence,
        )
