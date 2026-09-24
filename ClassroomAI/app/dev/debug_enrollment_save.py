"""
Enrollment Save Pipeline Tracer
---------------------------------
Traces the exact production save path step by step and verifies that the
embedding is actually persisted to the database.

Does NOT modify any production code.

Usage:
    py -3 app/dev/debug_enrollment_save.py --student-id 1 --photo "C:/path/to/photo.jpg"

If --photo is omitted the script stops after the DB check (no camera opens).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np

from app.database.connection import SessionLocal
from app.models.student import Student


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _sep(label: str = "") -> None:
    if label:
        print(f"\n── STEP: {label} {'─' * max(1, 50 - len(label))}")
    else:
        print("─" * 60)


def _read_student(student_id: int) -> None:
    """Re-open a fresh session and print the raw face_encoding from the DB."""
    db = SessionLocal()
    try:
        s = db.query(Student).filter(Student.id == student_id).first()
        if s is None:
            print(f"   !! Student id={student_id} not found in DB")
            return
        raw = s.face_encoding
        print(f"   id            : {s.id}")
        print(f"   name          : {s.name}")
        print(f"   is_active     : {s.is_active}")
        print(f"   face_encoding : {repr(raw[:80]) if raw else 'NULL / None'}")
        if raw:
            try:
                data = json.loads(raw)
                outer_len = len(data)
                if outer_len and isinstance(data[0], list):
                    inner_len = len(data[0])
                    print(f"   JSON structure: list of {outer_len} embedding(s), each len={inner_len}")
                elif outer_len:
                    print(f"   JSON structure: flat list of {outer_len} values")
                else:
                    print("   JSON structure: empty list — !! PROBLEM")
            except Exception as e:
                print(f"   !! JSON parse error: {e}")
        else:
            print("   !! face_encoding is NULL / empty — nothing was persisted")
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# Main trace
# ──────────────────────────────────────────────────────────────────────────────

def run_trace(student_id: int, photo_path: str) -> None:
    print("=" * 60)
    print("ENROLLMENT SAVE PIPELINE TRACE")
    print("=" * 60)

    # ── Pre-check: what is in the DB before we start ──────────────
    _sep("0 — DB STATE BEFORE ENROLLMENT")
    print("  Reading student BEFORE any save attempt:")
    _read_student(student_id)

    # ── Step 1: Load image bytes ──────────────────────────────────
    _sep("1 — LOAD IMAGE FROM DISK")
    if not os.path.exists(photo_path):
        print(f"  !! File not found: {photo_path}")
        return
    image_bytes = open(photo_path, "rb").read()
    print(f"  File            : {photo_path}")
    print(f"  Size            : {len(image_bytes):,} bytes")

    # ── Step 2: Face detection + embedding ───────────────────────
    _sep("2 — FACE DETECTION  (FaceExtractor.extract_from_bytes)")
    from app.ai.face.face_extractor import FaceExtractor, RejectionReason
    extractor = FaceExtractor()
    result = extractor.extract_from_bytes(image_bytes)

    print(f"  result.accepted          : {result.accepted}")
    print(f"  result.rejection_reason  : {result.rejection_reason}")

    if not result.accepted:
        print(f"\n  !! STOPPED: face extraction rejected — {result.rejection_reason}")
        return

    raw_embedding = result.embedding.embedding  # list[float]

    # ── Step 3: Embedding details ─────────────────────────────────
    _sep("3 — EMBEDDING DETAILS")
    arr = np.array(raw_embedding, dtype=np.float64)
    print(f"  Type            : {type(raw_embedding).__name__}")
    print(f"  Length          : {len(raw_embedding)}")
    print(f"  Shape (as array): {arr.shape}")
    print(f"  Dtype (as array): {arr.dtype}")
    print(f"  Norm            : {np.linalg.norm(arr):.6f}")
    print(f"  Min / Max       : {arr.min():.6f} / {arr.max():.6f}")
    print(f"  First 5 values  : {arr[:5].tolist()}")
    print(f"  Last  5 values  : {arr[-5:].tolist()}")

    # ── Step 4: JSON serialisation ────────────────────────────────
    _sep("4 — JSON THAT WILL BE STORED")
    json_to_store = json.dumps([raw_embedding])
    print(f"  json.dumps([embedding]) length : {len(json_to_store)} chars")
    print(f"  First 120 chars                : {json_to_store[:120]}…")

    # Verify roundtrip
    parsed_back = json.loads(json_to_store)
    restored = np.array(parsed_back[0], dtype=np.float64)
    diff = np.max(np.abs(arr - restored))
    print(f"  JSON roundtrip max diff        : {diff:.2e}  {'✓ OK' if diff < 1e-10 else '!! LOSSY'}")

    # ── Step 5: SQLAlchemy field assignment ───────────────────────
    _sep("5 — SQLALCHEMY FIELD ASSIGNMENT")
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == student_id).first()
        if student is None:
            print(f"  !! Student id={student_id} not found — cannot save")
            return

        print(f"  Student found   : id={student.id}  name='{student.name}'")
        print(f"  face_encoding BEFORE assignment : {repr(student.face_encoding)}")

        student.face_encoding = json_to_store
        print(f"  face_encoding AFTER  assignment : {repr(student.face_encoding[:80])}…")

        # Check dirty state before commit
        from sqlalchemy import inspect as sa_inspect
        insp = sa_inspect(student)
        dirty_attrs = {
            attr.key: (attr.history.deleted, attr.history.added)
            for attr in insp.attrs
            if attr.history.has_changes()
        }
        print(f"  SQLAlchemy dirty attributes    : {list(dirty_attrs.keys())}")

        # ── Step 6: Commit ────────────────────────────────────────
        _sep("6 — db.commit()")
        try:
            db.commit()
            print("  db.commit() completed without exception")
        except Exception as exc:
            print(f"  !! db.commit() RAISED: {type(exc).__name__}: {exc}")
            db.rollback()
            return

        # ── Step 7: Read-back in the SAME session ─────────────────
        _sep("7 — READ-BACK (same session, db.refresh)")
        db.refresh(student)
        print(f"  face_encoding after refresh : {repr(student.face_encoding[:80]) if student.face_encoding else 'NULL'}")

    finally:
        db.close()

    # ── Step 8: Read-back in a FRESH session ─────────────────────
    _sep("8 — READ-BACK (fresh session — ultimate truth)")
    _read_student(student_id)

    print("\n" + "=" * 60)
    print("TRACE COMPLETE")
    print("=" * 60)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Enrollment save pipeline tracer")
    parser.add_argument("--student-id", type=int, required=True, help="Student DB id (pk)")
    parser.add_argument("--photo", type=str, required=True, help="Path to the photo file")
    args = parser.parse_args()

    run_trace(student_id=args.student_id, photo_path=args.photo)


if __name__ == "__main__":
    main()
