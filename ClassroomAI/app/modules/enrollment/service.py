from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.ai.face.face_extractor import FaceExtractor, RejectionReason
from app.ai.face.face_recognition_service import FaceRecognitionService
from app.core.config import settings
from app.modules.cameras.models import CameraConfig
from app.modules.cameras.transport import OpenCvCameraTransport
from app.modules.enrollment.repository import EnrollmentRepository
from app.modules.enrollment.schemas import (
    EnrollmentStats,
    EnrollmentStatus,
    EnrollmentStatusResponse,
    PhotoEnrollmentResponse,
)

_SAMPLES_NEEDED = 20
_FRAME_INTERVAL = 0.1
_DUPLICATE_DISTANCE = 0.35


@dataclass
class _EnrollmentSession:
    student_id: int
    status: EnrollmentStatus = EnrollmentStatus.RUNNING
    samples_captured: int = 0
    samples_needed: int = _SAMPLES_NEEDED
    embeddings: list[list[float]] = field(default_factory=list)
    error: str = ""
    # Per-rejection counters
    stat_accepted: int = 0
    stat_blurry: int = 0
    stat_too_small: int = 0
    stat_no_face: int = 0
    stat_duplicate: int = 0
    _thread: threading.Thread | None = field(default=None, repr=False, compare=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)


class EnrollmentService:
    """Orchestrates the face enrollment workflow for a single student.

    Architecture:
        API  →  EnrollmentService  →  FaceExtractor  →  embeddings
                                   →  EnrollmentRepository  →  DB

    The service manages one enrollment session per student.  Each session runs
    a background thread that reads frames from the camera transport, delegates
    filtering and extraction to FaceExtractor, and stops automatically once
    the required number of samples has been collected.
    """

    def __init__(
        self,
        repository: EnrollmentRepository | None = None,
        extractor: FaceExtractor | None = None,
        face_service: FaceRecognitionService | None = None,
    ) -> None:
        self._repository = repository or EnrollmentRepository()
        self._extractor = extractor or FaceExtractor()
        self._face_service = face_service or FaceRecognitionService()
        self._sessions: dict[int, _EnrollmentSession] = {}
        self._lock = threading.Lock()

    def start(self, student_id: int, db: Session) -> EnrollmentStatusResponse:
        with self._lock:
            existing = self._sessions.get(student_id)
            if existing and existing.status == EnrollmentStatus.RUNNING:
                return self._to_response(existing)

            student = self._repository.find_student(db, student_id)
            if student is None:
                raise ValueError(f"Student {student_id} not found")

            session = _EnrollmentSession(student_id=student_id)
            self._sessions[student_id] = session

        thread = threading.Thread(
            target=self._capture_loop,
            args=(session, db),
            daemon=True,
            name=f"enrollment-{student_id}",
        )
        session._thread = thread
        thread.start()
        return self._to_response(session)

    def stop(self, student_id: int) -> EnrollmentStatusResponse:
        with self._lock:
            session = self._sessions.get(student_id)
            if session is None:
                raise ValueError(f"No enrollment session found for student {student_id}")
            session._stop.set()
            if session.status == EnrollmentStatus.RUNNING:
                session.status = EnrollmentStatus.IDLE
        return self._to_response(session)

    def status(self, student_id: int) -> EnrollmentStatusResponse:
        with self._lock:
            session = self._sessions.get(student_id)
            if session is None:
                return EnrollmentStatusResponse(
                    student_id=student_id,
                    status=EnrollmentStatus.IDLE,
                    samples_captured=0,
                    samples_needed=_SAMPLES_NEEDED,
                    message="No enrollment session started",
                )
        return self._to_response(session)

    def _capture_loop(self, session: _EnrollmentSession, db: Session) -> None:
        transport = OpenCvCameraTransport()
        config = CameraConfig(
            camera_id=f"enroll-{session.student_id}",
            name="Enrollment webcam",
            source=0,
        )
        try:
            transport.connect(config)
        except Exception as exc:
            with self._lock:
                session.status = EnrollmentStatus.FAILED
                session.error = str(exc)
            return

        try:
            while not session._stop.is_set() and session.samples_captured < session.samples_needed:
                try:
                    frame_obj = transport.read_frame()
                except Exception:
                    time.sleep(_FRAME_INTERVAL)
                    continue

                if frame_obj is None:
                    time.sleep(_FRAME_INTERVAL)
                    continue

                result = self._extractor.extract(frame_obj.frame)

                if not result.accepted:
                    with self._lock:
                        if result.rejection_reason == RejectionReason.BLURRY:
                            session.stat_blurry += 1
                        elif result.rejection_reason == RejectionReason.TOO_SMALL:
                            session.stat_too_small += 1
                        else:
                            session.stat_no_face += 1
                    time.sleep(_FRAME_INTERVAL)
                    continue

                embedding = result.embedding.embedding  # type: ignore[union-attr]

                if self._is_duplicate(embedding, session.embeddings):
                    with self._lock:
                        session.stat_duplicate += 1
                    time.sleep(_FRAME_INTERVAL)
                    continue

                with self._lock:
                    session.embeddings.append(embedding)
                    session.samples_captured += 1
                    session.stat_accepted += 1

                time.sleep(_FRAME_INTERVAL)

            if not session._stop.is_set() and session.samples_captured >= session.samples_needed:
                validated = self._validate_embeddings(session.embeddings)
                self._repository.save_embeddings(db, session.student_id, validated)
                with self._lock:
                    session.status = EnrollmentStatus.COMPLETE
        except Exception as exc:
            with self._lock:
                session.status = EnrollmentStatus.FAILED
                session.error = str(exc)
        finally:
            transport.disconnect()

    def enroll_from_photo(
        self,
        student_id: int,
        image_bytes: bytes,
        filename: str,
        db: Session,
    ) -> PhotoEnrollmentResponse:
        """Enroll a student from a single uploaded image.

        Validates that the image contains exactly one face, generates the
        embedding via FaceRecognitionService, saves it to the database, and
        optionally persists the image file.
        """
        student = self._repository.find_student(db, student_id)
        if student is None:
            raise ValueError(f"Student {student_id} not found")

        try:
            encodings = self._face_service.encode_face_from_bytes(image_bytes)
        except Exception as exc:
            raise ValueError(f"Image processing failed: {exc}") from exc

        if not encodings:
            raise ValueError("No face detected in the uploaded image")
        if len(encodings) > 1:
            raise ValueError(
                f"Multiple faces detected ({len(encodings)}). "
                "Upload a photo containing exactly one face."
            )

        embedding: list[float] = (
            encodings[0].tolist() if hasattr(encodings[0], "tolist") else list(encodings[0])
        )

        photo_path = self._save_photo(student_id, image_bytes, filename)
        self._repository.save_photo_embedding(db, student_id, embedding, photo_path)

        return PhotoEnrollmentResponse(
            success=True,
            student_id=student_id,
            face_detected=True,
            embedding_saved=True,
            photo_path=photo_path,
        )

    def register_face(
        self,
        student_id: int,
        image_bytes: bytes,
        filename: str,
        db: Session,
    ) -> PhotoEnrollmentResponse:
        """Production face registration with full quality gating.

        Unlike enroll_from_photo (which delegates quality checks to
        FaceRecognitionService), this method uses FaceExtractor which enforces
        blur detection, minimum face size, and single-face validation before
        generating the embedding.  Saves the original image under
        uploads/enrollment/{student_id}/.
        """
        student = self._repository.find_student(db, student_id)
        if student is None:
            raise ValueError(f"Student {student_id} not found")

        result = self._extractor.extract_from_bytes(image_bytes)
        if not result.accepted:
            _reason_messages = {
                "no_face":        "No face detected in the uploaded image.",
                "multiple_faces": "Multiple faces detected. Upload a photo with exactly one face.",
                "too_small":      "Face is too small. Use a closer or higher-resolution photo.",
                "blurry":         "Face is too blurry. Use a sharper photo.",
                "no_encoding":    "Could not generate a face embedding from the image.",
            }
            reason = result.rejection_reason.value if result.rejection_reason else "unknown"
            raise ValueError(_reason_messages.get(reason, f"Face validation failed: {reason}"))

        embedding: list[float] = result.embedding.embedding  # type: ignore[union-attr]
        photo_path = self._save_registration_photo(student_id, image_bytes, filename)
        self._repository.save_photo_embedding(db, student_id, embedding, photo_path)

        return PhotoEnrollmentResponse(
            success=True,
            student_id=student_id,
            face_detected=True,
            embedding_saved=True,
            photo_path=photo_path,
        )

    def _save_photo(self, student_id: int, image_bytes: bytes, filename: str) -> str:
        upload_dir = Path(settings.UPLOAD_DIR) / "enrollment"
        upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix or ".jpg"
        dest = upload_dir / f"student_{student_id}_{uuid.uuid4().hex}{suffix}"
        dest.write_bytes(image_bytes)
        return str(dest)

    def _save_registration_photo(self, student_id: int, image_bytes: bytes, filename: str) -> str:
        """Save to a per-student subfolder: uploads/enrollment/{student_id}/."""
        student_dir = Path(settings.UPLOAD_DIR) / "enrollment" / str(student_id)
        student_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix or ".jpg"
        dest = student_dir / f"{uuid.uuid4().hex}{suffix}"
        dest.write_bytes(image_bytes)
        return str(dest)

    @staticmethod
    def _is_duplicate(
        embedding: list[float],
        existing: list[list[float]],
        threshold: float = _DUPLICATE_DISTANCE,
    ) -> bool:
        """Return True when *embedding* is too similar to any already-accepted sample.

        Uses L2 (Euclidean) distance in the 128-d face embedding space.
        No face_recognition import needed — this is pure numpy.
        """
        if not existing:
            return False
        arr = np.array(embedding, dtype=np.float32)
        known = np.array(existing, dtype=np.float32)
        distances = np.linalg.norm(known - arr, axis=1)
        return bool(np.min(distances) < threshold)

    @staticmethod
    def _validate_embeddings(embeddings: list[list[float]]) -> list[list[float]]:
        """Final deduplication pass before persisting.

        Re-runs the duplicate check on the collected batch so that any race
        conditions in the capture loop cannot produce near-identical entries.
        """
        validated: list[list[float]] = []
        for emb in embeddings:
            arr = np.array(emb, dtype=np.float32)
            if not any(
                bool(np.linalg.norm(np.array(v, dtype=np.float32) - arr) < _DUPLICATE_DISTANCE)
                for v in validated
            ):
                validated.append(emb)
        return validated

    @staticmethod
    def _to_response(session: _EnrollmentSession) -> EnrollmentStatusResponse:
        return EnrollmentStatusResponse(
            student_id=session.student_id,
            status=session.status,
            samples_captured=session.samples_captured,
            samples_needed=session.samples_needed,
            message=session.error,
            stats=EnrollmentStats(
                accepted=session.stat_accepted,
                rejected_blurry=session.stat_blurry,
                rejected_too_small=session.stat_too_small,
                rejected_no_face=session.stat_no_face,
                rejected_duplicate=session.stat_duplicate,
            ),
        )
