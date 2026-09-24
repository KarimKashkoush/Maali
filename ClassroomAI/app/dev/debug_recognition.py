"""
Recognition Pipeline Debugger
------------------------------
Traces the complete recognition pipeline:

  Database → Embedding Loading → Face Detection → Distance → Decision

Prints a full diagnostic for every detected face and every DB record.
Does NOT modify any production code.

Run from the repository root:
    py -3 app/dev/debug_recognition.py
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cv2
import face_recognition
import numpy as np

from app.core.config import settings
from app.database.connection import SessionLocal
from app.models.student import Student


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1 — DB probe: raw inspection before any recognition code runs
# ──────────────────────────────────────────────────────────────────────────────

def probe_database() -> list[dict]:
    """Query the real DB and print every student's embedding status."""

    print("=" * 60)
    print("STEP 1 — DATABASE PROBE")
    print(f"  DATABASE_URL : {settings.DATABASE_URL}")

    # Resolve the actual file path for SQLite
    if settings.DATABASE_URL.startswith("sqlite:///./"):
        db_file = os.path.join(ROOT, settings.DATABASE_URL[len("sqlite:///./"):])
        print(f"  Resolved path: {db_file}")
        print(f"  File exists  : {os.path.exists(db_file)}")

    db = SessionLocal()
    enrolled: list[dict] = []
    try:
        all_students = db.query(Student).all()
        print(f"\n  Total students in DB : {len(all_students)}")

        if not all_students:
            print("  !! No students found at all — have you run the migrations?")
            return enrolled

        for s in all_students:
            raw = s.face_encoding
            has_encoding = raw is not None

            # Parse and validate the encoding
            parsed_shape = None
            parse_error = None
            parsed_array = None
            raw_preview = None

            if has_encoding:
                raw_preview = raw[:80] + ("…" if len(raw) > 80 else "")
                try:
                    data = json.loads(raw)
                    if not data:
                        parse_error = "empty list after JSON decode"
                    elif isinstance(data[0], list):
                        arr = np.mean(data, axis=0).astype(np.float32)
                        parsed_shape = arr.shape
                        parsed_array = arr
                        parse_error = None if parsed_shape == (128,) else f"unexpected shape {parsed_shape}"
                    else:
                        arr = np.array(data, dtype=np.float32)
                        parsed_shape = arr.shape
                        parsed_array = arr
                        parse_error = None if parsed_shape == (128,) else f"unexpected shape {parsed_shape}"
                except Exception as exc:
                    parse_error = str(exc)

            print(f"\n  ── Student id={s.id}  ext={s.external_student_id}  "
                  f"name='{s.name}'  is_active={s.is_active}")
            print(f"     face_encoding present : {has_encoding}")
            if has_encoding:
                print(f"     raw (first 80 chars)  : {raw_preview}")
                if parse_error:
                    print(f"     !! PARSE ERROR        : {parse_error}")
                else:
                    print(f"     parsed shape          : {parsed_shape}")
                    print(f"     embedding norm        : {np.linalg.norm(parsed_array):.4f}")

                if parsed_array is not None and parse_error is None:
                    enrolled.append({
                        "student_id":          s.id,
                        "external_student_id": s.external_student_id,
                        "name":                s.name,
                        "embedding":           parsed_array,
                    })
    finally:
        db.close()

    # Re-run with the exact same filter the RecognitionRepository uses
    db2 = SessionLocal()
    try:
        filtered = (
            db2.query(Student)
            .filter(
                Student.face_encoding.isnot(None),
                Student.is_active == True,  # noqa: E712
            )
            .all()
        )
        print(f"\n  Students matching recognition filter (active + has encoding): {len(filtered)}")
        if len(filtered) == 0 and len(all_students) > 0:
            print("  !! Filter returned 0 — possible causes:")
            print("     • is_active is False / 0 for enrolled students")
            print("     • face_encoding is stored as empty string, not NULL")
            # Extra check: students with encoding but not active
            for s in all_students:
                if s.face_encoding and not s.is_active:
                    print(f"     → id={s.id} '{s.name}' has encoding but is_active=False")
                if s.face_encoding == "":
                    print(f"     → id={s.id} '{s.name}' face_encoding is empty string (not NULL)")
    finally:
        db2.close()

    print(f"\n  Embeddings available for recognition : {len(enrolled)}")
    print("=" * 60)
    return enrolled


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2 — Live camera trace
# ──────────────────────────────────────────────────────────────────────────────

def run_debug_camera(enrolled: list[dict]) -> None:
    tolerance = settings.FACE_MATCH_TOLERANCE

    print("\nSTEP 2 — LIVE CAMERA TRACE")
    print(f"  Tolerance (FACE_MATCH_TOLERANCE) : {tolerance}")
    print(f"  Enrolled faces loaded            : {len(enrolled)}")
    if not enrolled:
        print("  !! No embeddings loaded — recognition will always return UNKNOWN")
        print("     Register a face first via: POST /students/{id}/register-face")
    print("  Press Q to quit\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam.")
        return

    frame_n = 0
    last_print = 0.0

    while True:
        ok, frame_bgr = cap.read()
        if not ok or frame_bgr is None:
            continue

        frame_n += 1
        now = time.monotonic()

        # Detect and encode every face
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb, model="hog")
        encodings = face_recognition.face_encodings(rgb, locations)

        # Draw on frame
        display = frame_bgr.copy()
        for (top, right, bottom, left), enc in zip(locations, encodings):
            # ── per-face recognition trace (printed once per second) ──
            if now - last_print >= 1.0:
                _print_face_trace(enc, enrolled, tolerance)
                last_print = now

            # Determine label for display
            label, color = _decide(enc, enrolled, tolerance)
            cv2.rectangle(display, (left, top), (right, bottom), color, 2)
            cv2.putText(display, label, (left, max(top - 10, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)

        cv2.putText(display, f"Faces: {len(locations)}  Enrolled: {len(enrolled)}",
                    (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imshow("Recognition Debugger  |  Q to quit", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def _print_face_trace(
    enc: np.ndarray,
    enrolled: list[dict],
    tolerance: float,
) -> None:
    print("  ────────────────────────────────────────────")
    print(f"  Detected face embedding norm : {np.linalg.norm(enc):.4f}")
    print(f"  Enrolled students loaded     : {len(enrolled)}")

    if not enrolled:
        print("  Match                        : NO (no embeddings to compare)")
        return

    best_dist   = float("inf")
    best_name   = None
    best_ext_id = None
    best_sid    = None

    for kf in enrolled:
        dist = float(face_recognition.face_distance([kf["embedding"]], enc)[0])
        flag = "← best" if dist < best_dist else ""
        print(f"    Student id={kf['student_id']:3d}  ext={kf['external_student_id']:6d}"
              f"  name='{kf['name']}'")
        print(f"      Embedding shape : {kf['embedding'].shape}  "
              f"norm={np.linalg.norm(kf['embedding']):.4f}")
        print(f"      Distance        : {dist:.6f}  {flag}")
        if dist < best_dist:
            best_dist   = dist
            best_name   = kf["name"]
            best_ext_id = kf["external_student_id"]
            best_sid    = kf["student_id"]

    matched = best_dist <= tolerance
    print(f"  Best match  : id={best_sid}  ext={best_ext_id}  name='{best_name}'")
    print(f"  Best dist   : {best_dist:.6f}")
    print(f"  Threshold   : {tolerance}")
    print(f"  Match       : {'YES ✓' if matched else 'NO ✗  (dist > threshold)'}")
    if not matched:
        margin = best_dist - tolerance
        print(f"  Margin over threshold: +{margin:.6f}")
        if best_dist > 0.8:
            print("  !! Very high distance — the stored embedding likely belongs")
            print("     to a different person or was corrupted during storage.")
        elif best_dist > tolerance:
            print(f"  !! Distance {best_dist:.4f} is close but exceeds tolerance {tolerance}.")
            print(f"     Try raising FACE_MATCH_TOLERANCE in .env (current={tolerance}).")


def _decide(
    enc: np.ndarray,
    enrolled: list[dict],
    tolerance: float,
) -> tuple[str, tuple[int, int, int]]:
    if not enrolled:
        return "UNKNOWN", (0, 0, 220)
    best_dist = float("inf")
    best_name = "UNKNOWN"
    for kf in enrolled:
        d = float(face_recognition.face_distance([kf["embedding"]], enc)[0])
        if d < best_dist:
            best_dist = d
            best_name = kf["name"]
    if best_dist <= tolerance:
        conf = int((1.0 - best_dist) * 100)
        return f"{best_name}  {conf}%", (0, 200, 0)
    return "UNKNOWN", (0, 0, 220)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    enrolled = probe_database()
    run_debug_camera(enrolled)


if __name__ == "__main__":
    main()
