import json
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.ai.face.face_recognition_service import FaceMatch, FaceRecognitionService, UnknownFace
from app.core.config import settings
from app.core.enums import AttendanceStatus, EventType
from app.models.attendance import AttendanceRecord
from app.models.session import ClassSession
from app.models.session_event import SessionEvent
from app.models.student import Student
from app.schemas.attendance import FrameProcessResponse, IdentificationResult


class FrameProcessor:
    def __init__(self, db: Session, face_service: FaceRecognitionService | None = None):
        self.db = db
        self.face_service = face_service or FaceRecognitionService()

    def process_frame(self, session: ClassSession, image_bytes: bytes) -> FrameProcessResponse:
        frame_encodings = self.face_service.encode_face_from_bytes(image_bytes)
        students = (
            self.db.query(Student)
            .filter(
                Student.class_id == session.class_id,
                Student.is_active.is_(True),
                Student.face_encoding.isnot(None),
            )
            .all()
        )

        known_encodings: list[np.ndarray] = []
        known_metadata: list[tuple[int, int, str]] = []
        for student in students:
            if student.face_encoding:
                known_encodings.append(self.face_service.deserialize_encoding(student.face_encoding))
                known_metadata.append(
                    (student.id, student.external_student_id, student.name)
                )

        matches = self.face_service.identify_faces(
            frame_encodings=frame_encodings,
            known_encodings=known_encodings,
            known_metadata=known_metadata,
            tolerance=settings.FACE_MATCH_TOLERANCE,
        )

        identifications: list[IdentificationResult] = []
        attendance_updates = 0
        students_identified = 0
        now = datetime.utcnow()

        for match in matches:
            if isinstance(match, FaceMatch):
                if match.confidence < settings.FACE_MIN_CONFIDENCE:
                    continue

                students_identified += 1
                identifications.append(
                    IdentificationResult(
                        student_id=match.student_id,
                        external_student_id=match.external_student_id,
                        student_name=match.student_name,
                        confidence=round(match.confidence, 4),
                        is_known=True,
                    )
                )

                updated = self._update_attendance(session, match, now)
                if updated:
                    attendance_updates += 1

                self._log_event(
                    session_id=session.id,
                    student_id=match.student_id,
                    event_type=EventType.STUDENT_IDENTIFIED,
                    confidence=match.confidence,
                    metadata={"distance": match.distance},
                    timestamp=now,
                )
            else:
                identifications.append(
                    IdentificationResult(
                        student_id=None,
                        external_student_id=None,
                        student_name=None,
                        confidence=round(match.confidence, 4),
                        is_known=False,
                    )
                )
                self._log_event(
                    session_id=session.id,
                    student_id=None,
                    event_type=EventType.UNKNOWN_FACE,
                    confidence=match.confidence,
                    metadata={},
                    timestamp=now,
                )

        self.db.commit()

        return FrameProcessResponse(
            session_id=session.id,
            faces_detected=len(frame_encodings),
            students_identified=students_identified,
            attendance_updates=attendance_updates,
            identifications=identifications,
        )

    def _get_or_create_attendance(
        self, session_id: int, student_id: int
    ) -> AttendanceRecord:
        record = (
            self.db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == student_id,
            )
            .first()
        )
        if record:
            return record

        record = AttendanceRecord(
            session_id=session_id,
            student_id=student_id,
            status=AttendanceStatus.ABSENT.value,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def _update_attendance(
        self, session: ClassSession, match: FaceMatch, now: datetime
    ) -> bool:
        record = self._get_or_create_attendance(session.id, match.student_id)
        record.detection_count += 1
        record.last_seen_at = now
        record.recognition_confidence = match.confidence

        if record.first_seen_at is None:
            record.first_seen_at = now

        if record.detection_count < settings.FACE_CONFIRM_FRAMES:
            return False

        late_threshold = session.started_at + timedelta(minutes=settings.LATE_GRACE_MINUTES)

        if record.status == AttendanceStatus.ABSENT.value:
            if now <= late_threshold:
                record.status = AttendanceStatus.PRESENT.value
                record.check_in_at = now
                event_type = EventType.ATTENDANCE_MARKED
            else:
                record.status = AttendanceStatus.LATE.value
                record.check_in_at = now
                record.late_minutes = max(
                    0, int((now - session.started_at).total_seconds() // 60)
                    - settings.LATE_GRACE_MINUTES
                )
                event_type = EventType.LATE_ARRIVAL

            self._log_event(
                session_id=session.id,
                student_id=match.student_id,
                event_type=event_type,
                confidence=match.confidence,
                metadata={"status": record.status},
                timestamp=now,
            )
            return True

        if record.status == AttendanceStatus.LEFT.value:
            record.status = AttendanceStatus.RETURNED.value
            self._log_event(
                session_id=session.id,
                student_id=match.student_id,
                event_type=EventType.RETURNED,
                confidence=match.confidence,
                metadata={},
                timestamp=now,
            )
            return True

        return False

    def _log_event(
        self,
        session_id: int,
        student_id: int | None,
        event_type: EventType,
        confidence: float | None,
        metadata: dict,
        timestamp: datetime,
    ) -> None:
        event = SessionEvent(
            session_id=session_id,
            student_id=student_id,
            event_type=event_type.value,
            confidence=confidence,
            metadata_json=json.dumps(metadata),
            timestamp=timestamp,
        )
        self.db.add(event)
