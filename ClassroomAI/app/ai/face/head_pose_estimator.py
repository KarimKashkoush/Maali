from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import face_recognition
import numpy as np


class HeadPose(str, Enum):
    FRONT   = "front"
    LEFT    = "left"    # person's left (camera right)
    RIGHT   = "right"   # person's right (camera left)
    UP      = "up"
    DOWN    = "down"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class PoseResult:
    """Result of head pose estimation for a single frame."""

    pose: HeadPose
    face_location: tuple[int, int, int, int]  # (top, right, bottom, left) for drawing
    yaw_ratio: float    # [-1, 1]; positive = person's LEFT, negative = person's RIGHT
    pitch_ratio: float  # [-1, 1]; positive = looking UP, negative = looking DOWN
    face_detected: bool


# ── Classification thresholds ─────────────────────────────────────────────────
# Increase _YAW_THRESH if LEFT/RIGHT triggers too easily (e.g., 0.22).
# Increase _PITCH_THRESH if UP/DOWN triggers too easily (e.g., 0.22).
_YAW_THRESH   = 0.18
_PITCH_THRESH = 0.18

# Neutral pitch offset: expected (nose_y − eye_y) / eye_span when the face is
# looking straight at the camera.  Approximately 0.40 for a typical laptop
# webcam sitting at eye level.  Raise this if UP is triggered too easily from
# a neutral position; lower it if DOWN is triggered too easily.
_NEUTRAL_PITCH = 0.40

# Sensitivity multiplier for pitch.
_PITCH_SCALE = 2.5


class HeadPoseEstimator:
    """Estimates head pose using face_recognition (dlib) 2D landmarks.

    This implementation has NO dependency on MediaPipe or any additional
    package beyond the face_recognition library that is already used for
    face embeddings.

    Algorithm
    ---------
    *YAW (left / right)*:
        Horizontal offset of the nose tip from the midpoint between both eyes,
        normalised by the inter-eye span.

        Convention (face_recognition uses person-centric naming):
          'left_eye'  = person's left eye → appears on CAMERA RIGHT (higher x)
          'right_eye' = person's right eye → appears on CAMERA LEFT  (lower x)

        When the person turns LEFT their nose moves to camera-right →
        (nose_x − eye_mid_x) > 0 → positive yaw → HeadPose.LEFT ✓

    *PITCH (up / down)*:
        Vertical distance of the nose tip below the eye midpoint, normalised
        by the inter-eye span.

        When looking UP the face rotates around the eye axis so the nose rises
        toward eye level → d_eye_nose decreases → (_NEUTRAL − d_eye_nose) > 0
        → positive pitch → HeadPose.UP ✓

        When looking DOWN the nose drops further → negative pitch ✓

    Tuning
    ------
    Adjust _YAW_THRESH, _PITCH_THRESH, _NEUTRAL_PITCH, _PITCH_SCALE at the
    top of this module without touching any other file.  The wizard and the
    demo consume only the HeadPose enum and PoseResult dataclass.
    """

    def estimate(self, frame_bgr: np.ndarray) -> PoseResult:
        """Estimate head pose from a BGR camera frame.

        Always returns a PoseResult; check .face_detected before using pose.
        """
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])

        locations = face_recognition.face_locations(rgb, model="hog")
        if not locations:
            return PoseResult(
                pose=HeadPose.UNKNOWN,
                face_location=(0, 0, 0, 0),
                yaw_ratio=0.0,
                pitch_ratio=0.0,
                face_detected=False,
            )

        # Pass pre-computed location so dlib skips re-detection
        all_landmarks = face_recognition.face_landmarks(
            rgb,
            face_locations=[locations[0]],
            model="large",
        )
        if not all_landmarks:
            return PoseResult(
                pose=HeadPose.UNKNOWN,
                face_location=locations[0],
                yaw_ratio=0.0,
                pitch_ratio=0.0,
                face_detected=False,
            )

        yaw, pitch = self._compute_ratios(all_landmarks[0])
        pose = self._classify(yaw, pitch)

        return PoseResult(
            pose=pose,
            face_location=locations[0],
            yaw_ratio=round(yaw, 3),
            pitch_ratio=round(pitch, 3),
            face_detected=True,
        )

    def close(self) -> None:
        """No resources to release — face_recognition is stateless."""

    @staticmethod
    def _compute_ratios(
        lm: dict[str, list[tuple[int, int]]],
    ) -> tuple[float, float]:
        left_eye_c  = np.mean(lm["left_eye"],  axis=0, dtype=np.float32)
        right_eye_c = np.mean(lm["right_eye"], axis=0, dtype=np.float32)
        nose_c      = np.mean(lm["nose_tip"],  axis=0, dtype=np.float32)
        eye_mid     = (left_eye_c + right_eye_c) / 2.0

        eye_span = float(abs(left_eye_c[0] - right_eye_c[0]))
        if eye_span < 4.0:
            return 0.0, 0.0

        # YAW: rightward nose deviation from eye midpoint (image x-axis)
        yaw = float(np.clip((nose_c[0] - eye_mid[0]) / eye_span, -1.0, 1.0))

        # PITCH: nose sits below eye level; d_eye_nose shrinks when looking up
        d_eye_nose_norm = float(nose_c[1] - eye_mid[1]) / eye_span
        pitch = float(np.clip(
            (_NEUTRAL_PITCH - d_eye_nose_norm) * _PITCH_SCALE,
            -1.0, 1.0,
        ))

        return yaw, pitch

    @staticmethod
    def _classify(yaw: float, pitch: float) -> HeadPose:
        if abs(yaw) < _YAW_THRESH and abs(pitch) < _PITCH_THRESH:
            return HeadPose.FRONT
        if abs(yaw) >= abs(pitch):
            return HeadPose.LEFT if yaw > 0 else HeadPose.RIGHT
        return HeadPose.UP if pitch > 0 else HeadPose.DOWN

