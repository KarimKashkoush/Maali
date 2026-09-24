from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord
from app.models.student import Student


class AttendanceRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_session_attendance(self, session_id: int):
        return (
            self.db.query(AttendanceRecord, Student)
            .join(Student, Student.id == AttendanceRecord.student_id)
            .filter(AttendanceRecord.session_id == session_id)
            .order_by(Student.name)
            .all()
        )

    def get_by_session_and_student(self, session_id: int, student_id: int) -> AttendanceRecord | None:
        return (
            self.db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == student_id,
            )
            .first()
        )

    def add(self, record: AttendanceRecord) -> AttendanceRecord:
        self.db.add(record)
        return record
