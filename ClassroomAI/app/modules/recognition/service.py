from __future__ import annotations

import logging
import threading

import face_recognition
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.recognition.repository import KnownFace, RecognitionRepository

logger = logging.getLogger(__name__)
from app.modules.recognition.schemas import FaceHit


class RecognitionService:
    """Identifies all faces in a BGR camera frame against the known-student database.

    This service is the only layer that calls face_recognition for matching.
    It never touches OpenCV — it receives numpy arrays from the pipeline and
    returns structured FaceHit results that callers can display or process.

    The in-memory cache of known faces must be refreshed periodically by
    calling reload_known_faces(db).  The pipeline is responsible for timing.
    """

    def __init__(
        self,
        repository: RecognitionRepository | None = None,
        tolerance: float | None = None,
    ) -> None:
        self._repo = repository or RecognitionRepository()
        self._tolerance = tolerance if tolerance is not None else settings.FACE_MATCH_TOLERANCE
        self._known_faces: list[KnownFace] = []
        self._lock = threading.Lock()

    def reload_known_faces(self, db: Session) -> int:
        """Refresh the in-memory embedding cache from the database.

        Returns the number of enrolled students loaded.
        """
        faces = self._repo.get_all_enrolled(db)
        with self._lock:
            self._known_faces = faces
        return len(faces)

    def load_known_faces(self, faces: list[KnownFace]) -> None:
        """Directly set the in-memory known-face list (no DB access).

        Used by the live attendance manager to inject a pre-built,
        classroom-scoped embedding list without going through the repository.
        """
        with self._lock:
            self._known_faces = list(faces)

    def identify_frame(self, frame: np.ndarray) -> list[FaceHit]:
        """Detect and identify every face in a BGR camera frame.

        Returns one FaceHit per detected face.  Matched hits carry student
        identity and confidence; unmatched hits have matched=False and the
        face_location for display purposes.
        """
        with self._lock:
            known = list(self._known_faces)

        # Convert BGR → RGB and ensure C-contiguous buffer for dlib 20.x
        rgb = np.ascontiguousarray(frame[:, :, ::-1])

        locations = face_recognition.face_locations(rgb, model="hog")
        if not locations:
            return []

        encodings = face_recognition.face_encodings(rgb, locations)
        return [self._match(loc, enc, known) for loc, enc in zip(locations, encodings)]

    def _match(
        self,
        location: tuple[int, int, int, int],
        encoding: np.ndarray,
        known_faces: list[KnownFace],
    ) -> FaceHit:
        if not known_faces:
            return FaceHit(
                face_location=location,
                matched=False,
                student_id=None,
                external_student_id=None,
                student_name=None,
                confidence=0.0,
            )

        known_encodings = [k.embedding for k in known_faces]
        distances = face_recognition.face_distance(known_encodings, encoding)

        # Group by student_id to log best per-image score per student
        if logger.isEnabledFor(logging.DEBUG):
            student_best: dict[int, tuple[float, str, str]] = {}  # id -> (dist, name, img_type)
            for kf, dist in zip(known_faces, distances):
                sid = kf.student_id
                if sid not in student_best or float(dist) < student_best[sid][0]:
                    student_best[sid] = (float(dist), kf.name, kf.image_type)
            logger.debug("[FACE-RECOGNITION] Detected face – comparing:")
            for sid, (dist, name, img_type) in student_best.items():
                logger.debug(
                    f"  {name}: best={max(0.0, 1.0 - dist):.2f} ({img_type})"
                )

        # Several reference photos may belong to one student.  Compare the
        # best distance for each distinct student so a match is not accepted
        # merely because a student has more reference photos in the cache.
        best_by_student: dict[int, tuple[float, KnownFace]] = {}
        for candidate, distance in zip(known_faces, distances):
            value = float(distance)
            previous = best_by_student.get(candidate.external_student_id)
            if previous is None or value < previous[0]:
                best_by_student[candidate.external_student_id] = (value, candidate)

        ranked = sorted(best_by_student.values(), key=lambda item: item[0])
        best_dist, kf = ranked[0]
        confidence = round(max(0.0, 1.0 - best_dist), 4)
        runner_up_distance = ranked[1][0] if len(ranked) > 1 else None
        is_unambiguous = (
            runner_up_distance is None
            or runner_up_distance - best_dist >= settings.FACE_MATCH_MIN_MARGIN
        )

        if (
            best_dist <= self._tolerance
            and confidence >= settings.FACE_MIN_CONFIDENCE
            and is_unambiguous
        ):
            logger.info(
                f"[FACE-RECOGNITION] MATCH: {kf.name} "
                f"image={kf.image_type} confidence={confidence:.2f} "
                f"(tolerance={self._tolerance})"
            )
            return FaceHit(
                face_location=location,
                matched=True,
                student_id=kf.student_id,
                external_student_id=kf.external_student_id,
                student_name=kf.name,
                confidence=confidence,
            )

        logger.debug(
            "[FACE-RECOGNITION] Rejected face: "
            f"best_distance={best_dist:.3f}, confidence={confidence:.2f}, "
            f"runner_up={runner_up_distance}, unambiguous={is_unambiguous}"
        )
        return FaceHit(
            face_location=location,
            matched=False,
            student_id=None,
            external_student_id=None,
            student_name=None,
            confidence=confidence,
        )
