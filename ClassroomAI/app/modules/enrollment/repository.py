from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.student import Student


class EnrollmentRepository:
    """Database operations for enrollment.  No business logic lives here."""

    def find_student(self, db: Session, student_id: int) -> Student | None:
        return db.query(Student).filter(Student.id == student_id).first()

    def save_embeddings(
        self,
        db: Session,
        student_id: int,
        embeddings: list[list[float]],
    ) -> None:
        """Persist all collected embeddings as JSON.

        The existing schema stores a single face_encoding field.  We serialise
        all sample embeddings as a JSON array so that future recognition code
        can average or vote across them without a schema migration.
        """
        student = self.find_student(db, student_id)
        if student is None:
            raise ValueError(f"Student {student_id} not found")
        student.face_encoding = json.dumps(embeddings)
        db.commit()

    def save_photo_embedding(
        self,
        db: Session,
        student_id: int,
        embedding: list[float],
        photo_path: str | None = None,
    ) -> None:
        """Persist a single photo-sourced embedding, wrapped in a one-item list.

        Stores the embedding in the same format as save_embeddings so that
        downstream recognition code can treat both sources uniformly.
        """
        student = self.find_student(db, student_id)
        if student is None:
            raise ValueError(f"Student {student_id} not found")
        student.face_encoding = json.dumps([embedding])
        if photo_path is not None:
            student.photo_path = photo_path
        db.commit()
