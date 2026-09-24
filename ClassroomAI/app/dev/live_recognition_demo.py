"""
Live Recognition Demo
---------------------
Production-backed desktop debugging tool.

Uses the REAL production pipeline:
  CameraTransport → StreamManager → RecognitionService → RecognitionRepository → DB

Displays live webcam with:
  • Green box  + Student Name + ID + Confidence%  → matched student
  • Red box    + UNKNOWN                           → unregistered face

This file adds ONLY the OpenCV display layer on top of the production
RecognitionPipeline.  No face_recognition calls live here.

Run from the repository root:
    py -3 app/dev/live_recognition_demo.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cv2
import numpy as np

from app.modules.cameras.models import CameraConfig
from app.modules.cameras.transport import OpenCvCameraTransport
from app.modules.recognition.pipeline import RecognitionPipeline
from app.modules.recognition.repository import RecognitionRepository
from app.modules.recognition.schemas import FaceHit
from app.modules.recognition.service import RecognitionService

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------
COLOR_MATCH   = (0, 200, 0)   # BGR green  — recognised student
COLOR_UNKNOWN = (0, 0, 220)   # BGR red    — unknown face
FONT          = cv2.FONT_HERSHEY_SIMPLEX
BOX_THICK     = 2
FONT_SCALE    = 0.60
FONT_THICK    = 2


def _draw_hit(display: np.ndarray, hit: FaceHit) -> None:
    top, right, bottom, left = hit.face_location
    color = COLOR_MATCH if hit.matched else COLOR_UNKNOWN

    cv2.rectangle(display, (left, top), (right, bottom), color, BOX_THICK)

    if hit.matched:
        line1 = f"{hit.student_name}"
        line2 = f"ID: {hit.external_student_id}  {int(hit.confidence * 100)}%"
    else:
        line1 = "UNKNOWN"
        line2 = ""

    y = max(top - 22, 18)
    cv2.putText(display, line1, (left, y), FONT, FONT_SCALE, color, FONT_THICK, cv2.LINE_AA)
    if line2:
        cv2.putText(display, line2, (left, y + 20), FONT, FONT_SCALE - 0.1, color, FONT_THICK, cv2.LINE_AA)


def main() -> None:
    transport = OpenCvCameraTransport()
    service   = RecognitionService(RecognitionRepository())
    pipeline  = RecognitionPipeline(transport, service)

    config = CameraConfig(
        camera_id="dev-recognition",
        name="Live Recognition Webcam",
        source=0,
    )

    print("==================================")
    print("Live Recognition Demo")
    print("Loading known faces from database…")
    pipeline.start(config)

    # Wait briefly for the pipeline to load faces and grab the first frame
    time.sleep(2.0)

    status_info = pipeline.get_status()
    print(f"Pipeline status : {status_info['status']}")
    if status_info["last_error"]:
        print(f"Error           : {status_info['last_error']}")
        pipeline.stop()
        sys.exit(1)

    print("Press Q to quit")
    print("==================================")

    prev_frame_count = 0
    fps_time = time.monotonic()
    fps_display = 0.0

    while True:
        frame, hits = pipeline.get_latest()

        if frame is None:
            # Pipeline not yet ready — show a blank waiting frame
            waiting = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                waiting,
                "Connecting to camera…",
                (140, 240),
                FONT, 0.8, (200, 200, 200), 2, cv2.LINE_AA,
            )
            cv2.imshow("Live Recognition  |  Q to quit", waiting)
            if cv2.waitKey(30) & 0xFF == ord("q"):
                break
            continue

        display = frame.copy()
        for hit in hits:
            _draw_hit(display, hit)

        # HUD
        status_info = pipeline.get_status()
        now         = time.monotonic()
        elapsed     = now - fps_time
        if elapsed >= 1.0:
            current = status_info["frames_processed"]
            fps_display = (current - prev_frame_count) / elapsed
            prev_frame_count = current
            fps_time = now

        cv2.putText(
            display,
            f"Frames: {status_info['frames_processed']}  FPS: {fps_display:.1f}",
            (10, 26), FONT, 0.55, (255, 255, 255), 1, cv2.LINE_AA,
        )
        if status_info["last_error"]:
            cv2.putText(
                display,
                f"ERR: {status_info['last_error'][:60]}",
                (10, display.shape[0] - 10), FONT, 0.45, (0, 60, 255), 1, cv2.LINE_AA,
            )

        cv2.imshow("Live Recognition  |  Q to quit", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    pipeline.stop()
    cv2.destroyAllWindows()
    print("Pipeline stopped. Goodbye.")


if __name__ == "__main__":
    main()
