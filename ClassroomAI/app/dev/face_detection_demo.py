"""
Face Detection Demo
-------------------
Standalone desktop debugging tool.
Opens the laptop webcam, detects faces in every frame, and draws a
bounding box + "UNKNOWN" label above each detected face.

Press Q to quit.

Purpose: verify the face detection pipeline works correctly before
         implementing recognition.

Run from the repository root:
    py -3 app/dev/face_detection_demo.py
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Bootstrap: make the repository root importable when running as a script
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cv2
import face_recognition
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0          # 0 = default laptop webcam
DETECT_EVERY_N = 2        # run face detection every N frames (keeps UI smooth)
BOX_COLOR = (0, 200, 0)   # BGR green
TEXT_COLOR = (0, 200, 0)
BOX_THICKNESS = 2
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.7
FONT_THICKNESS = 2
LABEL = "UNKNOWN"


def run() -> None:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera (index {CAMERA_INDEX})")
        sys.exit(1)

    print("==================================")
    print("Face Detection Demo")
    print("Press Q to quit")
    print("==================================")

    frame_count = 0
    face_locations: list[tuple[int, int, int, int]] = []

    while True:
        ok, frame_bgr = cap.read()
        if not ok or frame_bgr is None:
            print("WARNING: Failed to read frame — retrying")
            continue

        frame_count += 1

        # Run detection on every Nth frame; reuse previous locations otherwise
        if frame_count % DETECT_EVERY_N == 0:
            # face_recognition expects RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            # HOG model: fast on CPU, no GPU required
            face_locations = face_recognition.face_locations(frame_rgb, model="hog")

        # Draw bounding boxes and labels on the display frame
        display = frame_bgr.copy()
        for top, right, bottom, left in face_locations:
            cv2.rectangle(display, (left, top), (right, bottom), BOX_COLOR, BOX_THICKNESS)

            label_y = max(top - 10, 15)
            cv2.putText(
                display,
                LABEL,
                (left, label_y),
                FONT,
                FONT_SCALE,
                TEXT_COLOR,
                FONT_THICKNESS,
                cv2.LINE_AA,
            )

        face_count = len(face_locations)
        cv2.putText(
            display,
            f"Faces: {face_count}",
            (10, 28),
            FONT,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        cv2.imshow("Face Detection Demo  |  press Q to quit", display)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Camera released. Goodbye.")


if __name__ == "__main__":
    run()
