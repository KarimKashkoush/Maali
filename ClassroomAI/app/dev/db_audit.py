"""
Database Audit
--------------
Read-only inspection of the database.
Does NOT modify any code or data.

Run from the repository root:
    py -3 app/dev/db_audit.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text

from app.core.config import settings
from app.database.connection import SessionLocal, engine
from app.models.student import Student


def main() -> None:
    print("=" * 60)
    print("DATABASE AUDIT")
    print("=" * 60)

    # ── 1. Database URL ──────────────────────────────────────────
    print(f"\n1. DATABASE_URL\n   {settings.DATABASE_URL}")

    # ── 2. Resolved file path (SQLite only) ──────────────────────
    print("\n2. RESOLVED FILE PATH")
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///./"):
        path = os.path.join(ROOT, url[len("sqlite:///./"):])
    elif url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
    else:
        path = "(not SQLite)"
    print(f"   {path}")
    if path != "(not SQLite)":
        print(f"   Exists on disk : {os.path.exists(path)}")
        if os.path.exists(path):
            print(f"   Size           : {os.path.getsize(path):,} bytes")

    db = SessionLocal()
    try:
        # ── 3. Total students ─────────────────────────────────────
        all_students = db.query(Student).all()
        print(f"\n3. TOTAL STUDENTS\n   {len(all_students)}")

        # ── 4. Total with face_encoding ───────────────────────────
        with_encoding = [s for s in all_students if s.face_encoding is not None]
        print(f"\n4. STUDENTS WITH face_encoding\n   {len(with_encoding)}")

        # ── 5. Every student ──────────────────────────────────────
        print("\n5. STUDENT RECORDS")
        if not all_students:
            print("   (no students found)")
        for s in all_students:
            has = s.face_encoding is not None
            enc_len = len(s.face_encoding) if has else 0
            print(
                f"   id={s.id:<4d}  ext={s.external_student_id:<8d}  "
                f"is_active={str(s.is_active):<5}  "
                f"has_face_encoding={str(has):<5}  "
                f"encoding_chars={enc_len}"
            )
            print(f"         name='{s.name}'")

        # ── 6. Exact SQLAlchemy query ──────────────────────────────
        print("\n6. EXACT SQLALCHEMY QUERY USED BY RecognitionRepository")
        q = (
            db.query(Student)
            .filter(
                Student.face_encoding.isnot(None),
                Student.is_active == True,  # noqa: E712
            )
        )
        print(f"   {q}")

        # ── 7. Execute query and count ────────────────────────────
        rows = q.all()
        print(f"\n7. ROWS RETURNED BY QUERY\n   {len(rows)}")
        for r in rows:
            print(f"   → id={r.id}  name='{r.name}'  is_active={r.is_active}")

        # ── 8. Explain zero results ───────────────────────────────
        if len(rows) == 0:
            print("\n8. WHY ZERO ROWS")

            if not all_students:
                print("   REASON: The students table is empty.")
                print("   FIX   : Sync students via POST /api/v1/students/sync")
                return

            if not with_encoding:
                print("   REASON: No student has a face_encoding value.")
                print("   FIX   : Register a face via POST /students/{id}/register-face")
                return

            # Students exist with encodings — check each condition separately
            active_with_enc = [
                s for s in all_students
                if s.face_encoding is not None and s.is_active
            ]
            inactive_with_enc = [
                s for s in all_students
                if s.face_encoding is not None and not s.is_active
            ]
            empty_enc = [
                s for s in all_students
                if s.face_encoding == ""
            ]

            if inactive_with_enc:
                print("   REASON: Student(s) have a face_encoding but is_active=False/0.")
                for s in inactive_with_enc:
                    print(f"          id={s.id}  name='{s.name}'  is_active={s.is_active!r}")
                print("   FIX   : Set is_active=True for these students.")

            if empty_enc:
                print("   REASON: face_encoding is an empty string (not NULL).")
                print("          isnot(None) passes, but the JSON is empty.")
                for s in empty_enc:
                    print(f"          id={s.id}  name='{s.name}'")

            if active_with_enc:
                # Query passes both conditions manually but SQLAlchemy returns 0
                print("   REASON: Active students with encodings exist but the ORM")
                print("          query returned 0. Checking raw SQL…")
                raw = db.execute(
                    text(
                        "SELECT id, name, is_active, face_encoding IS NOT NULL AS has_enc "
                        "FROM students WHERE face_encoding IS NOT NULL AND is_active = 1"
                    )
                ).fetchall()
                print(f"   Raw SQL result: {len(raw)} rows")
                for row in raw:
                    print(f"          {row}")

            if not inactive_with_enc and not empty_enc and not active_with_enc:
                print("   REASON: Unknown. All students lack both is_active=True")
                print("          and a non-null face_encoding simultaneously.")
        else:
            print("\n8. DIAGNOSIS")
            print("   Query returned rows — embeddings are present.")
            print("   If recognition still shows UNKNOWN, run debug_recognition.py")
            print("   to check the distance vs threshold.")

    finally:
        db.close()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
