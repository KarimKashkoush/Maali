import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.ai.face_recognition_service import FaceRecognitionService
from app.core.config import settings
from app.models.student import Student
from app.schemas.student import StudentCreateRequest, StudentResponse, StudentSyncRequest


class StudentService:
    def __init__(self, db: Session, face_service: FaceRecognitionService | None = None):
        self.db = db
        self.face_service = face_service or FaceRecognitionService()
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def sync_students(self, payload: StudentSyncRequest) -> list[StudentResponse]:
        results: list[StudentResponse] = []
        for item in payload.students:
            results.append(self.upsert_student(item))
        self.db.commit()
        return results

    def upsert_student(self, payload: StudentCreateRequest) -> StudentResponse:
        student = (
            self.db.query(Student)
            .filter(Student.external_student_id == payload.external_student_id)
            .first()
        )

        if student:
            student.name = payload.name
            student.class_id = payload.class_id
            student.branch_id = payload.branch_id
            student.is_active = True
        else:
            student = Student(
                external_student_id=payload.external_student_id,
                name=payload.name,
                class_id=payload.class_id,
                branch_id=payload.branch_id,
                is_active=True,
            )
            self.db.add(student)

        self.db.flush()
        return self._to_response(student)

    async def register_face(self, external_student_id: int, photo: UploadFile) -> StudentResponse:
        student = (
            self.db.query(Student)
            .filter(Student.external_student_id == external_student_id)
            .first()
        )
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found. Sync student data first.",
            )

        suffix = Path(photo.filename or "photo.jpg").suffix or ".jpg"
        file_path = self.upload_dir / f"student_{external_student_id}_{uuid.uuid4().hex}{suffix}"
        content = await photo.read()
        file_path.write_bytes(content)

        try:
            encoding = self.face_service.encode_face_from_image(file_path)
        except ValueError as exc:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        student.face_encoding = self.face_service.serialize_encoding(encoding)
        student.photo_path = str(file_path)
        self.db.commit()
        self.db.refresh(student)
        return self._to_response(student)

    def list_students(self, class_id: int | None = None) -> list[StudentResponse]:
        query = self.db.query(Student).filter(Student.is_active.is_(True))
        if class_id is not None:
            query = query.filter(Student.class_id == class_id)
        students = query.order_by(Student.name).all()
        return [self._to_response(student) for student in students]

    def get_student(self, external_student_id: int) -> StudentResponse:
        student = (
            self.db.query(Student)
            .filter(Student.external_student_id == external_student_id)
            .first()
        )
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        return self._to_response(student)

    @staticmethod
    def _to_response(student: Student) -> StudentResponse:
        return StudentResponse(
            id=student.id,
            external_student_id=student.external_student_id,
            name=student.name,
            class_id=student.class_id,
            branch_id=student.branch_id,
            is_active=student.is_active,
            has_face_encoding=bool(student.face_encoding),
        )
