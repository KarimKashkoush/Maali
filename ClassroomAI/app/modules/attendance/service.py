from sqlalchemy.orm import Session

from app.core.enums import AttendanceStatus
from app.models.attendance import AttendanceRecord
from app.models.student import Student
from app.modules.attendance.repository import AttendanceRepository
from app.schemas.attendance import AttendanceRecordResponse


class AttendanceService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AttendanceRepository(db)

    def list_session_attendance(self, session_id: int) -> list[AttendanceRecordResponse]:
        records = self.repository.list_session_attendance(session_id)

        return [
            AttendanceRecordResponse(
                id=record.id,
                session_id=record.session_id,
                student_id=record.student_id,
                student_name=student.name,
                external_student_id=student.external_student_id,
                status=record.status,
                recognition_confidence=record.recognition_confidence,
                first_seen_at=record.first_seen_at,
                last_seen_at=record.last_seen_at,
                check_in_at=record.check_in_at,
                check_out_at=record.check_out_at,
                late_minutes=record.late_minutes,
                detection_count=record.detection_count,
            )
            for record, student in records
        ]

    def initialize_session_attendance(self, session_id: int, class_id: int) -> None:
        students = (
            self.db.query(Student)
            .filter(Student.class_id == class_id, Student.is_active.is_(True))
            .all()
        )

        for student in students:
            exists = self.repository.get_by_session_and_student(session_id, student.id)
            if exists:
                continue

            self.repository.add(
                AttendanceRecord(
                    session_id=session_id,
                    student_id=student.id,
                    status=AttendanceStatus.ABSENT.value,
                )
            )

        self.db.commit()
