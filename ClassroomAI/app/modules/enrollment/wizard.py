from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import numpy as np

from app.ai.face.face_extractor import FaceExtractor
from app.ai.face.head_pose_estimator import HeadPose, HeadPoseEstimator, PoseResult


# ── Constants ─────────────────────────────────────────────────────────────────
_CONFIRMATION_FRAMES = 8   # consecutive good frames needed to confirm a pose
_LIGHTING_MIN        = 40.0
_LIGHTING_MAX        = 220.0
_FACE_CENTER_MARGIN  = 0.30  # fraction of frame dimension for "centered" check

ALL_REQUIRED_POSES: tuple[HeadPose, ...] = (
    HeadPose.FRONT,
    HeadPose.LEFT,
    HeadPose.RIGHT,
    HeadPose.UP,
    HeadPose.DOWN,
)

POSE_INSTRUCTIONS: dict[HeadPose, str] = {
    HeadPose.FRONT: "Look straight at the camera",
    HeadPose.LEFT:  "Slowly turn your head LEFT",
    HeadPose.RIGHT: "Slowly turn your head RIGHT",
    HeadPose.UP:    "Tilt your head UP",
    HeadPose.DOWN:  "Tilt your head DOWN",
}


# ── Data classes ──────────────────────────────────────────────────────────────

class WizardState(str, Enum):
    WAITING_FACE = "waiting_face"   # no face / face not in guide circle
    COLLECTING   = "collecting"     # face centered, poses being captured
    COMPLETE     = "complete"       # all poses captured


@dataclass
class PoseSlot:
    pose: HeadPose
    completed: bool           = False
    embedding: list[float] | None = None
    confirmation_count: int   = 0       # frames accumulated for current run


@dataclass
class FrameQuality:
    face_in_circle:  bool  = False
    is_sharp:        bool  = False
    lighting_ok:     bool  = False
    is_large_enough: bool  = False

    @property
    def acceptable(self) -> bool:
        return self.face_in_circle and self.is_sharp and self.lighting_ok and self.is_large_enough


@dataclass
class WizardFrameResult:
    """Returned by process_frame — consumed by the UI layer for drawing."""

    state: WizardState
    pose_result: PoseResult
    quality: FrameQuality
    slots: list[PoseSlot]
    current_target_pose: HeadPose | None
    instruction: str
    completion_fraction: float               # 0.0 – 1.0
    confirmation_fraction: float             # 0.0 – 1.0 for current pose
    just_captured: HeadPose | None           # set for one frame when a pose is confirmed
    embeddings: list[list[float]] | None     # only set when complete


# ── Main wizard class ─────────────────────────────────────────────────────────

class EnrollmentWizard:
    """Guides the operator through capturing five head poses.

    This class contains NO display logic and NO OpenCV calls.  It receives
    numpy frames from any caller, delegates pose estimation and quality
    checking to the AI layer, and manages the state machine.

    The optional *on_complete* callback is invoked once, on the thread that
    calls process_frame, when all poses have been captured.  It receives the
    list of accepted embeddings (one per completed pose).

    This class is intentionally reusable: the same code powers both the
    standalone dev demo and the future production enrollment endpoint.
    """

    def __init__(
        self,
        required_poses: tuple[HeadPose, ...] = ALL_REQUIRED_POSES,
        confirmation_frames: int = _CONFIRMATION_FRAMES,
        on_complete: Callable[[list[list[float]]], None] | None = None,
    ) -> None:
        self._required_poses    = required_poses
        self._confirmation_frames = confirmation_frames
        self._on_complete       = on_complete

        self._estimator = HeadPoseEstimator()
        self._extractor = FaceExtractor()

        self._slots: dict[HeadPose, PoseSlot] = {
            p: PoseSlot(pose=p) for p in required_poses
        }
        self._state = WizardState.WAITING_FACE
        self._lock  = threading.Lock()
        self._just_captured: HeadPose | None = None

    # ── Public API ─────────────────────────────────────────────────────────

    def process_frame(self, frame_bgr: np.ndarray) -> WizardFrameResult:
        """Process one camera frame and advance the state machine."""
        with self._lock:
            return self._process(frame_bgr)

    def reset(self) -> None:
        """Reset the wizard to its initial state."""
        with self._lock:
            for slot in self._slots.values():
                slot.completed        = False
                slot.embedding        = None
                slot.confirmation_count = 0
            self._state = WizardState.WAITING_FACE
            self._just_captured = None

    @property
    def is_complete(self) -> bool:
        with self._lock:
            return self._state == WizardState.COMPLETE

    def close(self) -> None:
        self._estimator.close()

    # ── Internal ───────────────────────────────────────────────────────────

    def _process(self, frame: np.ndarray) -> WizardFrameResult:
        h, w = frame.shape[:2]
        pose_result = self._estimator.estimate(frame)

        # Determine face circle parameters (used for centering check)
        circle_cx, circle_cy = w // 2, h // 2
        circle_r = min(w, h) // 4

        quality = self._assess_quality(frame, pose_result, circle_cx, circle_cy, circle_r)
        just_captured = self._just_captured
        self._just_captured = None

        # ── State transitions ─────────────────────────────────────
        if self._state == WizardState.COMPLETE:
            pass  # stay complete

        elif not quality.face_in_circle:
            self._state = WizardState.WAITING_FACE
            self._reset_all_confirmation_counts()

        elif quality.acceptable:
            self._state = WizardState.COLLECTING
            just_captured = self._try_confirm_pose(frame, pose_result)

        # ── Build result ──────────────────────────────────────────
        pending  = self._pending_poses()
        target   = pending[0] if pending else None
        completed_count = sum(1 for s in self._slots.values() if s.completed)
        total    = len(self._slots)

        confirmation_frac = 0.0
        if target and self._state == WizardState.COLLECTING:
            slot = self._slots[target]
            if pose_result.pose == target:
                confirmation_frac = min(slot.confirmation_count / self._confirmation_frames, 1.0)

        if self._state == WizardState.COMPLETE:
            instruction = "Enrollment Complete!"
        elif not pose_result.face_detected:
            instruction = "Show your face to the camera"
        elif not quality.face_in_circle:
            instruction = "Move your face into the circle"
        elif not quality.lighting_ok:
            instruction = "Improve lighting — too dark or too bright"
        elif not quality.is_large_enough:
            instruction = "Move closer to the camera"
        elif target:
            instruction = POSE_INSTRUCTIONS.get(target, f"Pose: {target.value}")
        else:
            instruction = "Processing…"

        return WizardFrameResult(
            state=self._state,
            pose_result=pose_result,
            quality=quality,
            slots=list(self._slots.values()),
            current_target_pose=target,
            instruction=instruction,
            completion_fraction=completed_count / max(total, 1),
            confirmation_fraction=confirmation_frac,
            just_captured=just_captured,
            embeddings=self._get_embeddings() if self._state == WizardState.COMPLETE else None,
        )

    def _try_confirm_pose(
        self,
        frame: np.ndarray,
        pose_result: PoseResult,
    ) -> HeadPose | None:
        """Increment confirmation counter for current pose; confirm if threshold reached."""
        detected = pose_result.pose

        if detected not in self._slots:
            self._reset_all_confirmation_counts()
            return None

        slot = self._slots[detected]
        if slot.completed:
            # Already done — don't re-count
            self._reset_all_confirmation_counts(exclude=None)
            return None

        # Reset counts for all OTHER poses
        for p, s in self._slots.items():
            if p != detected:
                s.confirmation_count = 0

        slot.confirmation_count += 1

        if slot.confirmation_count >= self._confirmation_frames:
            # Quality + embedding extraction
            extraction = self._extractor.extract(frame)
            if extraction.accepted:
                slot.completed = True
                slot.embedding = extraction.embedding.embedding  # type: ignore[union-attr]
                slot.confirmation_count = 0
                self._just_captured = detected

                # Check completion
                if all(s.completed for s in self._slots.values()):
                    self._state = WizardState.COMPLETE
                    embeddings = self._get_embeddings()
                    if self._on_complete and embeddings:
                        self._on_complete(embeddings)

                return detected
            else:
                # Extraction failed despite passing preliminary quality
                slot.confirmation_count = 0

        return None

    def _assess_quality(
        self,
        frame: np.ndarray,
        pose_result: PoseResult,
        cx: int,
        cy: int,
        r: int,
    ) -> FrameQuality:
        q = FrameQuality()

        if not pose_result.face_detected:
            return q

        top, right, bottom, left = pose_result.face_location
        face_cx = (left + right) // 2
        face_cy = (top + bottom) // 2
        face_w  = right - left
        face_h  = bottom - top

        # Face center within guide circle
        dist = ((face_cx - cx) ** 2 + (face_cy - cy) ** 2) ** 0.5
        q.face_in_circle = dist <= r

        # Size check
        q.is_large_enough = face_w >= 80 and face_h >= 80

        # Lighting check (mean brightness of face region)
        if face_h > 0 and face_w > 0:
            face_roi = frame[max(top, 0):bottom, max(left, 0):right]
            if face_roi.size > 0:
                mean = float(np.mean(face_roi))
                q.lighting_ok = _LIGHTING_MIN <= mean <= _LIGHTING_MAX

        # Sharpness (Laplacian variance on face ROI — numpy-only, no cv2)
        if face_h > 0 and face_w > 0:
            face_roi = frame[max(top, 0):bottom, max(left, 0):right]
            if face_roi.size > 0:
                gray = np.mean(face_roi, axis=2).astype(np.float32) if face_roi.ndim == 3 else face_roi.astype(np.float32)
                q.is_sharp = _laplacian_variance(gray) >= 80.0

        return q

    def _pending_poses(self) -> list[HeadPose]:
        return [p for p in self._required_poses if not self._slots[p].completed]

    def _reset_all_confirmation_counts(self, exclude: HeadPose | None = None) -> None:
        for p, s in self._slots.items():
            if p != exclude:
                s.confirmation_count = 0

    def _get_embeddings(self) -> list[list[float]]:
        return [
            s.embedding
            for s in self._slots.values()
            if s.completed and s.embedding is not None
        ]


# ── Pure-numpy Laplacian variance (no cv2) ────────────────────────────────────

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
