from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from io import BytesIO

import face_recognition
import numpy as np


_BLUR_THRESHOLD = 80.0
_MIN_FACE_PX = 80


class RejectionReason(str, Enum):
    NO_FACE        = "no_face"
    MULTIPLE_FACES = "multiple_faces"
    TOO_SMALL      = "too_small"
    BLURRY         = "blurry"
    NO_ENCODING    = "no_encoding"


@dataclass(slots=True)
class FaceEmbedding:
    """One accepted face sample extracted from a single frame."""

    embedding: list[float]


@dataclass(slots=True)
class ExtractionResult:
    """Outcome of a single-frame extraction attempt."""

    embedding: FaceEmbedding | None
    rejection_reason: RejectionReason | None = None
    face_location: tuple[int, int, int, int] | None = None  # (top, right, bottom, left)

    @property
    def accepted(self) -> bool:
        return self.embedding is not None


class FaceExtractor:
    """Extracts a face embedding from a single frame.

    Filters out frames that contain no face, a face that is too small, or a
    face that is too blurry.  All face_recognition calls are isolated here.
    OpenCV is never used — callers of extract() pass BGR numpy arrays from
    the camera transport; callers of extract_from_bytes() pass raw image bytes.
    """

    def __init__(
        self,
        blur_threshold: float = _BLUR_THRESHOLD,
        min_face_px: int = _MIN_FACE_PX,
    ) -> None:
        self._blur_threshold = blur_threshold
        self._min_face_px = min_face_px

    def extract(self, frame: np.ndarray) -> ExtractionResult:
        """Extract from a BGR camera frame (e.g. from CameraTransport).

        Picks the first detected face; frames with multiple people are not
        rejected — only the best face is processed.  For strict single-face
        enforcement on uploaded images use extract_from_bytes().
        """
        rgb = np.ascontiguousarray(frame[:, :, ::-1] if frame.ndim == 3 else frame)
        return self._extract_rgb(rgb, require_single_face=False)

    def extract_from_bytes(self, image_bytes: bytes) -> ExtractionResult:
        """Extract from uploaded image bytes without using OpenCV.

        Enforces single-face requirement: returns MULTIPLE_FACES when more than
        one face is present so that the registration endpoint can reject bad
        photos before persisting anything.
        """
        rgb = np.ascontiguousarray(
            face_recognition.load_image_file(BytesIO(image_bytes))
        )
        return self._extract_rgb(rgb, require_single_face=True)

    def _extract_rgb(self, rgb: np.ndarray, *, require_single_face: bool) -> ExtractionResult:
        """Core quality-gating + embedding on a contiguous RGB array."""
        locations = face_recognition.face_locations(rgb)
        if not locations:
            return ExtractionResult(embedding=None, rejection_reason=RejectionReason.NO_FACE)

        if require_single_face and len(locations) > 1:
            return ExtractionResult(embedding=None, rejection_reason=RejectionReason.MULTIPLE_FACES)

        top, right, bottom, left = locations[0]
        if (bottom - top) < self._min_face_px or (right - left) < self._min_face_px:
            return ExtractionResult(
                embedding=None,
                rejection_reason=RejectionReason.TOO_SMALL,
                face_location=locations[0],
            )

        face_roi = rgb[top:bottom, left:right]
        if not self._is_sharp(face_roi):
            return ExtractionResult(
                embedding=None,
                rejection_reason=RejectionReason.BLURRY,
                face_location=locations[0],
            )

        encodings = face_recognition.face_encodings(rgb, known_face_locations=[locations[0]])
        if not encodings:
            return ExtractionResult(
                embedding=None,
                rejection_reason=RejectionReason.NO_ENCODING,
                face_location=locations[0],
            )

        return ExtractionResult(
            embedding=FaceEmbedding(embedding=encodings[0].tolist()),
            face_location=locations[0],
        )

    def _is_sharp(self, roi: np.ndarray) -> bool:
        gray = np.mean(roi, axis=2).astype(np.float32) if roi.ndim == 3 else roi.astype(np.float32)
        laplacian = self._laplacian_variance(gray)
        return laplacian >= self._blur_threshold

    @staticmethod
    def _laplacian_variance(gray: np.ndarray) -> float:
        kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        h, w = gray.shape
        kh, kw = kernel.shape
        ph, pw = kh // 2, kw // 2
        padded = np.pad(gray, ((ph, ph), (pw, pw)), mode="reflect")
        result = np.zeros((h, w), dtype=np.float32)
        for i in range(kh):
            for j in range(kw):
                result += kernel[i, j] * padded[i : i + h, j : j + w]
        return float(np.var(result))
