from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import numpy as np

from app.ai.face.face_extractor import FaceExtractor, RejectionReason


# ── Constants ─────────────────────────────────────────────────────────────────
_DEFAULT_TARGET_COUNT      = 5
_DEFAULT_UNIQUENESS_DIST   = 0.35   # L2 distance; embeddings closer than this are duplicates
_LIGHTING_MIN              = 40.0
_LIGHTING_MAX              = 220.0
_MIN_FACE_PX               = 80     # minimum face dimension in pixels


# ── Data classes ──────────────────────────────────────────────────────────────

class CoverageState(str, Enum):
    WAITING_FACE = "waiting_face"   # no face or quality gates fail
    COLLECTING   = "collecting"     # quality OK, actively accepting embeddings
    COMPLETE     = "complete"       # target count reached


@dataclass
class CoverageQuality:
    face_in_circle:  bool = False
    is_sharp:        bool = False
    lighting_ok:     bool = False
    is_large_enough: bool = False

    @property
    def acceptable(self) -> bool:
        return (
            self.face_in_circle
            and self.is_sharp
            and self.lighting_ok
            and self.is_large_enough
        )


@dataclass
class CoverageFrameResult:
    """Returned by CoverageEnrollmentService.process_frame — consumed by the UI."""

    state:                CoverageState
    quality:              CoverageQuality
    face_detected:        bool
    face_location:        tuple[int, int, int, int] | None  # (top, right, bottom, left)
    accepted_count:       int
    target_count:         int
    just_accepted:        bool         # True on the single frame a new embedding was accepted
    instruction:          str
    last_rejection:       str | None   # human-readable reason the last candidate was rejected
    embeddings:           list[list[float]] | None  # populated only when state == COMPLETE

    @property
    def completion_fraction(self) -> float:
        return self.accepted_count / max(self.target_count, 1)


# ── Service ───────────────────────────────────────────────────────────────────

class CoverageEnrollmentService:
    """Automatic coverage-based face enrollment.

    The student is NOT asked to perform specific poses.  Instead, the service
    continuously evaluates quality-gated frames and accepts each embedding that
    is sufficiently different from all previously accepted ones.  Enrollment
    finishes automatically when *target_count* unique views have been collected.

    Design
    ------
    - No coupling to OpenCV or any display library.
    - Input: raw BGR numpy frames from any camera source.
    - Output: CoverageFrameResult on every frame — the UI interprets this.
    - The optional *on_complete* callback fires once, on the calling thread,
      when the target count is reached.

    Uniqueness check
    ----------------
    Uses the L2 distance between 128-dimensional face embeddings.  If the
    minimum distance from a candidate to all previously accepted embeddings
    is below *uniqueness_threshold*, the candidate is discarded as a duplicate
    view.  A threshold of ~0.35 allows distinct angles of the same person while
    rejecting near-identical captures.

    Quality gates
    -------------
    1. Face detected inside the guide circle.
    2. Face region ≥ _MIN_FACE_PX in both dimensions.
    3. Mean brightness 40–220 (lighting check).
    4. Sharpness via FaceExtractor (Laplacian variance ≥ 80).
    """

    def __init__(
        self,
        target_count: int = _DEFAULT_TARGET_COUNT,
        uniqueness_threshold: float = _DEFAULT_UNIQUENESS_DIST,
        on_complete: Callable[[list[list[float]]], None] | None = None,
    ) -> None:
        self._target_count        = target_count
        self._uniqueness_threshold = uniqueness_threshold
        self._on_complete         = on_complete

        self._extractor  = FaceExtractor()
        self._accepted:  list[list[float]] = []
        self._state      = CoverageState.WAITING_FACE
        self._lock       = threading.Lock()
        self._just_accepted     = False
        self._last_rejection:   str | None = None

    # ── Public API ─────────────────────────────────────────────────────────

    def process_frame(self, frame_bgr: np.ndarray) -> CoverageFrameResult:
        """Evaluate one BGR camera frame and advance the state machine."""
        with self._lock:
            return self._process(frame_bgr)

    def reset(self) -> None:
        with self._lock:
            self._accepted.clear()
            self._state          = CoverageState.WAITING_FACE
            self._just_accepted  = False
            self._last_rejection = None

    @property
    def is_complete(self) -> bool:
        with self._lock:
            return self._state == CoverageState.COMPLETE

    # ── Internal ───────────────────────────────────────────────────────────

    def _process(self, frame: np.ndarray) -> CoverageFrameResult:
        h, w   = frame.shape[:2]
        cx, cy = w // 2, h // 2
        r      = min(w, h) // 4

        just_accepted   = self._just_accepted
        self._just_accepted = False

        # ── Short-circuit when already complete ──────────────────
        if self._state == CoverageState.COMPLETE:
            return CoverageFrameResult(
                state=CoverageState.COMPLETE,
                quality=CoverageQuality(),
                face_detected=False,
                face_location=None,
                accepted_count=len(self._accepted),
                target_count=self._target_count,
                just_accepted=just_accepted,
                instruction="Enrollment Complete!",
                last_rejection=None,
                embeddings=list(self._accepted),
            )

        # ── FaceExtractor: quality gates + embedding ──────────────
        extraction = self._extractor.extract(frame)

        face_location = extraction.face_location
        face_detected = face_location is not None

        # ── Geometric quality (requires face_location) ────────────
        quality = self._assess_quality(frame, face_location, cx, cy, r)

        # ── State machine ─────────────────────────────────────────
        if not quality.face_in_circle:
            self._state = CoverageState.WAITING_FACE

        elif quality.acceptable and extraction.accepted:
            self._state = CoverageState.COLLECTING
            embedding = extraction.embedding.embedding  # type: ignore[union-attr]

            if self._is_unique(embedding):
                self._accepted.append(embedding)
                self._just_accepted = True
                just_accepted       = True
                self._last_rejection = None

                if len(self._accepted) >= self._target_count:
                    self._state = CoverageState.COMPLETE
                    if self._on_complete:
                        self._on_complete(list(self._accepted))
            else:
                self._last_rejection = "Too similar to an existing view — keep moving"

        elif quality.acceptable and not extraction.accepted:
            self._state = CoverageState.COLLECTING
            reason = extraction.rejection_reason
            if reason == RejectionReason.BLURRY:
                self._last_rejection = "Blurry — hold still"
            elif reason == RejectionReason.TOO_SMALL:
                self._last_rejection = "Face too small — move closer"
            else:
                self._last_rejection = reason.value if reason else "extraction failed"

        # ── Instruction text ──────────────────────────────────────
        instruction = self._make_instruction(face_detected, quality)

        return CoverageFrameResult(
            state=self._state,
            quality=quality,
            face_detected=face_detected,
            face_location=face_location,
            accepted_count=len(self._accepted),
            target_count=self._target_count,
            just_accepted=just_accepted,
            instruction=instruction,
            last_rejection=self._last_rejection,
            embeddings=None,
        )

    def _assess_quality(
        self,
        frame: np.ndarray,
        face_location: tuple[int, int, int, int] | None,
        cx: int,
        cy: int,
        r: int,
    ) -> CoverageQuality:
        q = CoverageQuality()
        if face_location is None:
            return q

        top, right, bottom, left = face_location
        face_w = right  - left
        face_h = bottom - top
        face_cx = left + face_w // 2
        face_cy = top  + face_h // 2

        dist = ((face_cx - cx) ** 2 + (face_cy - cy) ** 2) ** 0.5
        q.face_in_circle  = dist <= r
        q.is_large_enough = face_w >= _MIN_FACE_PX and face_h >= _MIN_FACE_PX

        roi = frame[max(top, 0):bottom, max(left, 0):right]
        if roi.size > 0:
            mean = float(np.mean(roi))
            q.lighting_ok = _LIGHTING_MIN <= mean <= _LIGHTING_MAX
            q.is_sharp    = _laplacian_variance(
                np.mean(roi, axis=2).astype(np.float32) if roi.ndim == 3 else roi.astype(np.float32)
            ) >= 80.0

        return q

    def _is_unique(self, embedding: list[float]) -> bool:
        if not self._accepted:
            return True
        arr = np.array(embedding, dtype=np.float32)
        for prev in self._accepted:
            dist = float(np.linalg.norm(np.array(prev, dtype=np.float32) - arr))
            if dist < self._uniqueness_threshold:
                return False
        return True

    def _make_instruction(self, face_detected: bool, quality: CoverageQuality) -> str:
        if self._state == CoverageState.COMPLETE:
            return "Enrollment Complete!"
        if not face_detected:
            return "Show your face to the camera"
        if not quality.face_in_circle:
            return "Center your face in the circle"
        if not quality.lighting_ok:
            return "Improve lighting — too dark or too bright"
        if not quality.is_large_enough:
            return "Move closer to the camera"
        if not quality.is_sharp:
            return "Hold still — image is blurry"
        return "Move your head slowly while looking toward the camera"


# ── Standalone Laplacian variance (no cv2 dependency) ─────────────────────────

def _laplacian_variance(gray: np.ndarray) -> float:
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    h, w   = gray.shape
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2
    padded = np.pad(gray, ((ph, ph), (pw, pw)), mode="reflect")
    result = np.zeros((h, w), dtype=np.float32)
    for i in range(kh):
        for j in range(kw):
            result += kernel[i, j] * padded[i : i + h, j : j + w]
    return float(np.var(result))
