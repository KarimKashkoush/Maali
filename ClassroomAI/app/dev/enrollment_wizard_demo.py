"""
Smart Enrollment Wizard — Coverage Mode
-----------------------------------------
Automatic coverage-based enrollment.  The student simply moves their head
naturally while the system collects unique facial views.

Uses the REAL production components:
  CameraTransport -> CoverageEnrollmentService -> FaceExtractor

OpenCV is used ONLY for display in this file.

Usage:
    # Run wizard (display only, no DB save):
    py -3 app/dev/enrollment_wizard_demo.py

    # Run wizard and save embeddings for student id=1:
    py -3 app/dev/enrollment_wizard_demo.py --student-id 1

Press Q to quit at any time.
"""

from __future__ import annotations

import argparse
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
from app.modules.enrollment.coverage_service import (
    CoverageEnrollmentService,
    CoverageFrameResult,
    CoverageState,
)

_W, _H   = 960, 600
_PANEL_W = 280
_VIDEO_W = _W - _PANEL_W
_CIRCLE_R = min(_VIDEO_W, _H) // 4

_BG        = (18,  18,  28)
_PANEL_BG  = (22,  22,  34)
_GREEN     = (60,  220,  90)
_CYAN      = (0,   210, 255)
_YELLOW    = (0,   210, 255)
_RED       = (60,   60, 200)
_GREY      = (120, 120, 140)
_WHITE     = (255, 255, 255)
_CIRCLE_OK = (60,  180,  80)
_CIRCLE_NG = (80,   80, 120)
_FACE_OK   = (60,  220,  90)
_FACE_WARN = (0,   160, 220)
_FACE_BAD  = (60,   60, 200)
_BAR_FG    = (60,  200,  90)
_BAR_BG    = (50,   50,  70)
_FLASH_COL = (0,   220, 100)

_FONT      = cv2.FONT_HERSHEY_SIMPLEX
_FONT_BOLD = cv2.FONT_HERSHEY_DUPLEX


def _txt(img, text, xy, scale=0.55, color=_WHITE, thick=1, font=_FONT):
    cv2.putText(img, text, xy, font, scale, color, thick, cv2.LINE_AA)


def _bar(img, x, y, w, h, fraction, fg=_BAR_FG, bg=_BAR_BG):
    cv2.rectangle(img, (x, y), (x + w, y + h), bg, -1)
    filled = max(0, int(w * min(fraction, 1.0)))
    if filled > 0:
        cv2.rectangle(img, (x, y), (x + filled, y + h), fg, -1)


def _draw_guide(canvas, result, cx, cy):
    collecting = result.state == CoverageState.COLLECTING
    color      = _CIRCLE_OK if collecting else _CIRCLE_NG
    cv2.circle(canvas, (cx, cy), _CIRCLE_R, color, 2, cv2.LINE_AA)
    if collecting and result.completion_fraction > 0:
        angle = int(result.completion_fraction * 360)
        cv2.ellipse(canvas, (cx, cy), (_CIRCLE_R, _CIRCLE_R),
                    -90, 0, angle, _CYAN, 5, cv2.LINE_AA)


def _draw_face(canvas, result):
    if not result.face_detected or result.face_location is None:
        return
    top, right, bottom, left = result.face_location
    q = result.quality
    if q.face_in_circle and q.acceptable:
        color = _FACE_OK
    elif q.face_in_circle:
        color = _FACE_WARN
    else:
        color = _FACE_BAD
    cv2.rectangle(canvas, (left, top), (right, bottom), color, 2, cv2.LINE_AA)
    cv2.circle(canvas, ((left + right) // 2, (top + bottom) // 2), 4, color, -1, cv2.LINE_AA)


def _draw_instruction(canvas, result):
    text  = result.instruction
    color = _GREEN if result.state == CoverageState.COMPLETE else _WHITE
    scale = 0.60
    (tw, _), _ = cv2.getTextSize(text, _FONT_BOLD, scale, 2)
    cv2.putText(canvas, text, (max(10, (_VIDEO_W - tw) // 2), 34),
                _FONT_BOLD, scale, color, 2, cv2.LINE_AA)


def _draw_panel(canvas, result, flash_until):
    vw = _VIDEO_W
    canvas[:, vw:] = _PANEL_BG

    y = 28
    _txt(canvas, "ENROLLMENT", (vw + 20, y), 0.58, _YELLOW, 1, _FONT_BOLD)
    y += 36

    _txt(canvas, f"{result.accepted_count} / {result.target_count}  unique views",
         (vw + 16, y), 0.52, _WHITE)
    y += 22
    _bar(canvas, vw + 16, y, _PANEL_W - 32, 14, result.completion_fraction)
    y += 28

    cv2.line(canvas, (vw + 10, y), (vw + _PANEL_W - 10, y), (50, 50, 70), 1)
    y += 14

    _txt(canvas, "Quality", (vw + 16, y), 0.46, _GREY)
    y += 20
    q = result.quality
    for label, ok in [("Centered", q.face_in_circle), ("Sharp", q.is_sharp),
                       ("Lighting", q.lighting_ok), ("Face size", q.is_large_enough)]:
        _txt(canvas, ("[+] " if ok else "[ ] ") + label, (vw + 16, y), 0.46,
             _GREEN if ok else _RED)
        y += 20
    y += 6

    cv2.line(canvas, (vw + 10, y), (vw + _PANEL_W - 10, y), (50, 50, 70), 1)
    y += 14

    if flash_until > time.monotonic():
        _txt(canvas, "[+] New View Captured!", (vw + 12, y), 0.52, _FLASH_COL, 1, _FONT_BOLD)
    elif result.last_rejection:
        _txt(canvas, result.last_rejection[:32], (vw + 12, y), 0.40, _GREY)
    y += 22

    if result.state == CoverageState.COLLECTING and result.accepted_count < result.target_count:
        _txt(canvas, "Move head slowly", (vw + 16, y), 0.44, _GREY)


def _draw_complete_overlay(canvas, count):
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 0), (_VIDEO_W, _H), (20, 60, 20), -1)
    cv2.addWeighted(overlay, 0.45, canvas, 0.55, 0, canvas)
    msg = "ENROLLMENT COMPLETE"
    (tw, _), _ = cv2.getTextSize(msg, _FONT_BOLD, 0.95, 3)
    cv2.putText(canvas, msg, ((_VIDEO_W - tw) // 2, _H // 2 - 16),
                _FONT_BOLD, 0.95, _GREEN, 3, cv2.LINE_AA)
    sub = f"{count} unique views saved  |  Press Q to exit"
    (sw, _), _ = cv2.getTextSize(sub, _FONT, 0.52, 1)
    cv2.putText(canvas, sub, ((_VIDEO_W - sw) // 2, _H // 2 + 26),
                _FONT, 0.52, _WHITE, 1, cv2.LINE_AA)


def _draw_status(canvas, result):
    y = _H - 16
    q = result.quality
    x = 10
    for label, ok in [("Face", result.face_detected), ("Centered", q.face_in_circle),
                       ("Sharp", q.is_sharp), ("Lighting", q.lighting_ok),
                       ("Size", q.is_large_enough)]:
        _txt(canvas, f"[{'+'if ok else'-'}]{label}", (x, y), 0.40, _GREEN if ok else _RED)
        x += 100


def _make_save_callback(student_id):
    def _save(embeddings):
        from app.database.connection import SessionLocal
        from app.modules.enrollment.repository import EnrollmentRepository
        db   = SessionLocal()
        repo = EnrollmentRepository()
        try:
            repo.save_embeddings(db, student_id, embeddings)
            print(f"[Wizard] Saved {len(embeddings)} embeddings for student id={student_id}")
        except Exception as exc:
            print(f"[Wizard] DB save error: {exc}")
        finally:
            db.close()
    return _save


def main():
    parser = argparse.ArgumentParser(description="Coverage Enrollment Wizard")
    parser.add_argument("--student-id", type=int, default=None)
    parser.add_argument("--target",     type=int, default=5)
    args = parser.parse_args()

    service = CoverageEnrollmentService(
        target_count=args.target,
        on_complete=_make_save_callback(args.student_id) if args.student_id else None,
    )

    transport = OpenCvCameraTransport()
    transport.connect(CameraConfig(camera_id="wizard", name="Enrollment Wizard", source=0))

    print("=" * 52)
    print("Smart Enrollment Wizard - Coverage Mode")
    if args.student_id:
        print(f"Student ID  : {args.student_id}")
    print(f"Target views: {args.target}")
    print("Press Q to quit")
    print("=" * 52)

    flash_until = 0.0
    cx, cy = _VIDEO_W // 2, _H // 2

    try:
        while True:
            frame_obj = transport.read_frame()
            if frame_obj is None:
                continue

            frame  = cv2.resize(frame_obj.frame, (_VIDEO_W, _H))
            result = service.process_frame(frame)

            if result.just_accepted:
                flash_until = time.monotonic() + 1.5
                print(f"[+] View {result.accepted_count}/{result.target_count} captured")

            canvas = np.full((_H, _W, 3), _BG, dtype=np.uint8)
            canvas[:, :_VIDEO_W] = frame

            _draw_guide(canvas, result, cx, cy)
            _draw_face(canvas, result)
            _draw_panel(canvas, result, flash_until)
            _draw_instruction(canvas, result)
            _draw_status(canvas, result)

            if result.state == CoverageState.COMPLETE:
                _draw_complete_overlay(canvas, result.accepted_count)
                if not args.student_id:
                    print(f"[Wizard] {result.accepted_count} embeddings ready"
                          " (pass --student-id to save)")

            cv2.imshow("Enrollment Wizard - Coverage Mode  |  Q to quit", canvas)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        transport.disconnect()
        cv2.destroyAllWindows()
        print("Wizard closed.")


if __name__ == "__main__":
    main()
