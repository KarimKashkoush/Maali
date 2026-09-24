import json
from datetime import datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import ExportStatus
from app.models.export_log import ExportLog
from app.models.session import ClassSession
from app.schemas.attendance import ExportResponse
from app.modules.attendance.service import AttendanceService
from app.modules.sessions.service import SessionService


class ReportsService:
    """Placeholder service for future report generation workflows."""

    def __init__(self, db=None):
        self.db = db


class ExportService:
    def __init__(self, db: Session):
        self.db = db
        self.session_service = SessionService(db)
        self.attendance_service = AttendanceService(db)

    def export_session(self, session_id: int, target_url: str | None = None) -> ExportResponse:
        session = self.session_service.get_session(session_id)
        webhook_url = target_url or settings.SCHOOL_PLATFORM_WEBHOOK_URL

        if not webhook_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="School platform webhook URL is not configured",
            )

        attendance = self.attendance_service.list_session_attendance(session_id)
        report = self.session_service.get_report(session_id)

        payload = {
            "session_id": session.id,
            "external_session_id": session.external_session_id,
            "class_id": session.class_id,
            "teacher_id": session.teacher_id,
            "subject_id": session.subject_id,
            "branch_id": session.branch_id,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "exported_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_students": report.total_students,
                "present_count": report.present_count,
                "late_count": report.late_count,
                "absent_count": report.absent_count,
                "left_count": report.left_count,
                "average_confidence": report.average_confidence,
            },
            "attendance": [
                {
                    "external_student_id": item.external_student_id,
                    "student_name": item.student_name,
                    "status": item.status,
                    "check_in_at": item.check_in_at.isoformat() if item.check_in_at else None,
                    "check_out_at": item.check_out_at.isoformat() if item.check_out_at else None,
                    "late_minutes": item.late_minutes,
                    "recognition_confidence": item.recognition_confidence,
                }
                for item in attendance
            ],
        }

        headers = {"Content-Type": "application/json"}
        if settings.SCHOOL_PLATFORM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.SCHOOL_PLATFORM_API_KEY}"

        export_log = ExportLog(
            session_id=session_id,
            target_url=webhook_url,
            payload_json=json.dumps(payload),
            status=ExportStatus.PENDING.value,
        )
        self.db.add(export_log)
        self.db.flush()

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(webhook_url, json=payload, headers=headers)

            export_log.response_code = response.status_code
            if response.is_success:
                export_log.status = ExportStatus.SUCCESS.value
                message = "Attendance exported successfully"
            else:
                export_log.status = ExportStatus.FAILED.value
                export_log.error_message = response.text[:1000]
                message = f"Export failed with status {response.status_code}"
        except httpx.HTTPError as exc:
            export_log.status = ExportStatus.FAILED.value
            export_log.error_message = str(exc)
            message = f"Export failed: {exc}"

        self.db.commit()

        return ExportResponse(
            session_id=session_id,
            export_status=export_log.status,
            target_url=webhook_url,
            records_exported=len(attendance),
            message=message,
        )
