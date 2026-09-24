from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.models.student import Student


@dataclass
class KnownFace:
    """In-memory representation of a registered student embedding."""

    student_id: int
    external_student_id: int
    name: str
    embedding: np.ndarray  # shape (128,), dtype float32
    image_type: str = ""   # primary/front/left/right/up/down – for logging


class RecognitionRepository:
    """Loads registered student embeddings from the database.

    No business logic lives here.  The repository is the only place that
    reads face_encoding from the Student table for recognition purposes.
    """

    def get_enrolled_for_class(self, db: Session, class_id: int) -> list[KnownFace]:
        """Return KnownFace entries only for students in a specific classroom."""
        students = (
            db.query(Student)
            .filter(
                Student.face_encoding.isnot(None),
                Student.is_active == True,  # noqa: E712
                Student.class_id == class_id,
            )
            .all()
        )
        result: list[KnownFace] = []
        for s in students:
            embedding = self._parse_encoding(s.face_encoding)
            if embedding is None:
                continue
            result.append(
                KnownFace(
                    student_id=s.id,
                    external_student_id=s.external_student_id,
                    name=s.name,
                    embedding=embedding,
                )
            )
        return result

    def get_all_enrolled(self, db: Session) -> list[KnownFace]:
        """Return one KnownFace per active student that has a registered embedding.

        Embeddings may be stored as:
          - [[e1, e2, …]]          – single photo (one-element list of 128-d list)
          - [[e1, …], [e2, …], …]  – multi-frame webcam enrollment
          - [e1, e2, …]            – legacy flat list (from old register_face path)

        In all cases the result is the mean of all 128-d vectors, stored as a
        single float32 array so the recognition service can call
        face_recognition.face_distance() without further marshalling.
        """
        students = (
            db.query(Student)
            .filter(
                Student.face_encoding.isnot(None),
                Student.is_active == True,  # noqa: E712
            )
            .all()
        )
        result: list[KnownFace] = []
        for s in students:
            embedding = self._parse_encoding(s.face_encoding)
            if embedding is None:
                continue
            result.append(
                KnownFace(
                    student_id=s.id,
                    external_student_id=s.external_student_id,
                    name=s.name,
                    embedding=embedding,
                )
            )
        return result

    @staticmethod
    def _parse_encoding(raw: str | None) -> np.ndarray | None:
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if not data:
                return None
            if isinstance(data[0], list):
                # Multi-embedding format: average all samples
                return np.mean(data, axis=0).astype(np.float32)
            # Flat list (single embedding)
            return np.array(data, dtype=np.float32)
        except Exception:
            return None
