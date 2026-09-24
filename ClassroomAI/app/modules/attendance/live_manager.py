"""Live attendance manager: camera → recognition → WebSocket broadcast.

Each live attendance session owns:
  - A camera transport (OpenCvCameraTransport)
  - A recognition service loaded with classroom-scoped face embeddings
  - A background daemon thread running the recognition loop
  - A set of asyncio queues – one per connected WebSocket client

Thread → async bridge
---------------------
The recognition loop runs in a daemon thread.  When it detects a face it
needs to push an event to potentially many async WebSocket coroutines.

The bridge uses ``asyncio.AbstractEventLoop.call_soon_threadsafe``:

    loop.call_soon_threadsafe(queue.put_nowait, event)

Every WebSocket coroutine holds its own ``asyncio.Queue``.  When an event
arrives in the queue the coroutine immediately sends it to the client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import cv2
import face_recognition
import httpx
import numpy as np

from app.core.config import settings
from app.core.enums import AttendanceStatus
from app.core.school_clock import school_now, school_today
from app.database.connection import SessionLocal
from app.models.attendance import AttendanceRecord
from app.models.face_embedding import StudentFaceEmbedding
from app.models.session import ClassSession
from app.models.student import Student
from app.modules.cameras.exceptions import CameraConnectionError
from app.modules.cameras.models import CameraConfig
from app.modules.cameras.transport import OpenCvCameraTransport
from app.modules.recognition.repository import KnownFace, RecognitionRepository
from app.modules.recognition.service import RecognitionService

logger = logging.getLogger(__name__)

# Processing rate – keep low so the CPU isn't saturated while still
# delivering responsive attendance (~10 FPS is plenty for a classroom).
_FRAME_INTERVAL = 1.0 / 10.0  # seconds between frames

# After a student is confirmed present, suppress further "already present"
# broadcasts for this many seconds (prevents event flooding).
_COOLDOWN_DEFAULT = 30.0


# ---------------------------------------------------------------------------
# Internal dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _LiveSession:
    """All runtime state for one live attendance session."""

    session_id: int
    class_id: int
    total_students: int
    known_faces: list[KnownFace]

    # asyncio event loop captured at session creation (async context)
    loop: asyncio.AbstractEventLoop

    # per-student confirmation + cooldown tracking (keyed by external_student_id)
    confirmation_counts: dict[int, int] = field(default_factory=dict)
    last_confirmed_at: dict[int, float] = field(default_factory=dict)
    present_external_ids: set[int] = field(default_factory=set)
    is_late_capture: bool = False
    camera_mode: str = "browser"
    recognition_service: RecognitionService | None = None
    recognition_lock: threading.Lock = field(default_factory=threading.Lock)

    # unknown-face throttle: only broadcast every N unknown hits
    unknown_hit_count: int = 0

    # Thread synchronisation
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    # Camera transport – one per session
    transport: OpenCvCameraTransport | None = None

    # Connected WebSocket clients – each has its own asyncio.Queue
    queues: list[asyncio.Queue] = field(default_factory=list)
    queues_lock: threading.Lock = field(default_factory=threading.Lock)

    # Latest annotated JPEG frame for MJPEG streaming (single-frame buffer)
    latest_annotated_jpeg: bytes | None = None
    latest_frame_lock: threading.Lock = field(default_factory=threading.Lock)


# ---------------------------------------------------------------------------
# Helper – synchronous face encoding (run in executor from async context)
# ---------------------------------------------------------------------------


def _sync_encode_face(image_bytes: bytes) -> list[float] | None:
    """Decode an image and return the first face embedding, or None."""
    try:
        image = face_recognition.load_image_file(BytesIO(image_bytes))
        encodings = face_recognition.face_encodings(image)
        return encodings[0].tolist() if encodings else None
    except Exception as exc:  # corrupt image, dlib failure, etc.
        logger.debug(f"_sync_encode_face failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Manager singleton
# ---------------------------------------------------------------------------


class AttendanceLiveManager:
    """Manages all live attendance sessions for the application.

    Instantiated once at module import time and shared across requests.
    """

    def __init__(self) -> None:
        self._sessions: dict[int, _LiveSession] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public async API (called from FastAPI endpoints)
    # ------------------------------------------------------------------

    async def start_session(
        self,
        class_id: int,
        students: list[dict[str, Any]],
        camera_mode: str = "browser",
    ) -> dict[str, Any]:
        """Prepare embeddings, create DB session, start camera + recognition.

        ``students`` is a list of dicts with keys:
            external_id (int)   – Supabase student ID
            name        (str)   – student display name
            image_url   (str|None) – public URL for the student photo

        Returns a dict with ``session_id`` and ``status``.
        """
        # Build / refresh classroom face embeddings (may download from URLs)
        known_faces = await self._prepare_classroom_faces(class_id, students)

        # The first run creates ABSENT records for every active student. Later
        # camera openings reuse the same session and only add late arrivals.
        session_id, is_late_capture, present_ids = await asyncio.get_running_loop().run_in_executor(
            None, self._get_or_create_daily_session, class_id
        )

        with self._lock:
            if session_id in self._sessions:
                existing = self._sessions[session_id]
                return {
                    "session_id": session_id,
                    "status": "already_running",
                    "total_students": existing.total_students,
                    "enrolled_students": len({face.external_student_id for face in existing.known_faces}),
                }

        loop = asyncio.get_running_loop()
        transport = OpenCvCameraTransport() if camera_mode == "server" else None
        recognition_service = RecognitionService()
        recognition_service.load_known_faces(known_faces)

        session = _LiveSession(
            session_id=session_id,
            class_id=class_id,
            total_students=len(students),
            known_faces=known_faces,
            loop=loop,
            transport=transport,
            present_external_ids=present_ids,
            is_late_capture=is_late_capture,
            camera_mode=camera_mode,
            recognition_service=recognition_service,
        )

        with self._lock:
            self._sessions[session_id] = session

        if camera_mode == "server":
            thread = threading.Thread(
                target=self._recognition_loop,
                args=(session,),
                daemon=True,
                name=f"live-attendance-{session_id}",
            )
            session.thread = thread
            thread.start()

        logger.info(
            f"Live attendance started: session={session_id} class={class_id} "
            f"students={len(students)} enrolled={len(known_faces)}"
        )
        return {
            "session_id": session_id,
            "status": "running",
            "total_students": len(students),
            "enrolled_students": len({face.external_student_id for face in known_faces}),
        }

    def stop_session(self, session_id: int) -> dict[str, Any]:
        """Stop camera + recognition for a session.  Safe to call multiple times."""
        with self._lock:
            session = self._sessions.pop(session_id, None)

        if session is None:
            return {"status": "not_found"}

        session.stop_event.set()
        if session.thread:
            session.thread.join(timeout=6.0)

        # Finishing the first scan locks the initial absence decision but does
        # not close the daily record.  The camera may be opened again later to
        # register late arrivals in the same class/day.
        if not session.is_late_capture:
            self._complete_initial_roll_call(session_id)

        present_ids = list(session.present_external_ids)
        total = session.total_students
        absent_count = total - len(present_ids)

        completion_event = {
            "type": "attendance.completed",
            "session_id": session_id,
            "present_count": len(present_ids),
            "absent_count": absent_count,
            "present_external_ids": present_ids,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._broadcast(session, completion_event)

        # Signal all waiting WebSocket coroutines to exit
        self._close_all_clients(session)

        logger.info(
            f"Live attendance stopped: session={session_id} "
            f"present={len(present_ids)}/{total}"
        )
        return {
            "status": "completed",
            "session_id": session_id,
            "present_count": len(present_ids),
            "absent_count": absent_count,
        }

    def get_session_status(self, session_id: int) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        return {
            "session_id": session_id,
            "class_id": session.class_id,
            "total_students": session.total_students,
            "enrolled_students": len({face.external_student_id for face in session.known_faces}),
            "present_count": len(session.present_external_ids),
            "status": "running",
        }

    def subscribe_client(self, session_id: int) -> asyncio.Queue | None:
        """Register a new WebSocket client and return its event queue."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None

        queue: asyncio.Queue = asyncio.Queue()
        with session.queues_lock:
            session.queues.append(queue)
        return queue

    def unsubscribe_client(self, session_id: int, queue: asyncio.Queue) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return
        with session.queues_lock:
            if queue in session.queues:
                session.queues.remove(queue)

    def get_latest_jpeg(self, session_id: int) -> bytes | None:
        """Return the latest annotated JPEG frame for MJPEG streaming, or None."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        with session.latest_frame_lock:
            return session.latest_annotated_jpeg

    def is_session_active(self, session_id: int) -> bool:
        with self._lock:
            return session_id in self._sessions

    def process_browser_frame(self, session_id: int, image_bytes: bytes) -> dict[str, Any] | None:
        """Recognise one JPEG captured by the active board browser.

        The source image is decoded in memory only and discarded after this
        method returns; only attendance metadata is persisted.
        """
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None or session.camera_mode != "browser" or session.recognition_service is None:
            return None

        frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return {"frame_width": 0, "frame_height": 0, "detections": []}

        with session.recognition_lock:
            hits = session.recognition_service.identify_frame(frame)
            self._record_browser_hits(session, hits)

        return {
            "frame_width": int(frame.shape[1]),
            "frame_height": int(frame.shape[0]),
            "detections": [
                {
                    "top": hit.face_location[0],
                    "right": hit.face_location[1],
                    "bottom": hit.face_location[2],
                    "left": hit.face_location[3],
                    "matched": hit.matched,
                    "student_name": hit.student_name,
                    "confidence": round(hit.confidence, 3),
                }
                for hit in hits
            ],
        }

    def _record_browser_hits(self, session: _LiveSession, hits: list) -> None:
        """Confirm browser-camera matches and write only new attendance states."""
        now_mono = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()
        cooldown = getattr(settings, "ATTENDANCE_COOLDOWN_SECONDS", _COOLDOWN_DEFAULT)
        for hit in hits:
            if not hit.matched or hit.external_student_id is None or hit.student_id is None:
                continue
            external_id = hit.external_student_id
            session.confirmation_counts[external_id] = session.confirmation_counts.get(external_id, 0) + 1
            if session.confirmation_counts[external_id] < settings.FACE_CONFIRM_FRAMES:
                continue
            if now_mono - session.last_confirmed_at.get(external_id, 0.0) < cooldown:
                continue
            session.last_confirmed_at[external_id] = now_mono
            if external_id in session.present_external_ids:
                continue
            session.present_external_ids.add(external_id)
            self._mark_present_in_db(
                session.session_id, hit.student_id, hit.confidence, is_late=session.is_late_capture
            )
            self._broadcast(session, {
                "type": "student.recognized",
                "session_id": session.session_id,
                "student_id": external_id,
                "student_name": hit.student_name,
                "confidence": round(hit.confidence, 3),
                "present_count": len(session.present_external_ids),
                "total_students": session.total_students,
                "timestamp": now_iso,
            })

    # ------------------------------------------------------------------
    # Internal – broadcast helpers (thread-safe)
    # ------------------------------------------------------------------

    def _broadcast(self, session: _LiveSession, event: dict) -> None:
        """Push an event dict to every connected WebSocket client queue."""
        with session.queues_lock:
            queues = list(session.queues)
        for q in queues:
            try:
                session.loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:
                # Loop may be closed during shutdown – ignore
                pass

    def _close_all_clients(self, session: _LiveSession) -> None:
        """Send None sentinel so each WebSocket coroutine exits cleanly."""
        with session.queues_lock:
            queues = list(session.queues)
        for q in queues:
            try:
                session.loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    # Internal – frame annotation helper
    # ------------------------------------------------------------------

    @staticmethod
    def _annotate_frame(frame: np.ndarray, hits: list) -> np.ndarray:
        """Draw bounding boxes and names on a copy of the frame."""
        annotated = frame.copy()
        for hit in hits:
            top, right, bottom, left = hit.face_location
            if hit.matched and hit.student_name:
                color = (0, 180, 0)  # green – known student
                label = f"{hit.student_name} {int(hit.confidence * 100)}%"
            else:
                color = (0, 0, 210)  # red – unknown face
                label = "UNKNOWN"

            cv2.rectangle(annotated, (left, top), (right, bottom), color, 2)
            # label background
            cv2.rectangle(annotated, (left, bottom - 26), (right, bottom), color, cv2.FILLED)
            cv2.putText(
                annotated, label, (left + 4, bottom - 7),
                cv2.FONT_HERSHEY_DUPLEX, 0.5, (255, 255, 255), 1,
            )
        return annotated

    # ------------------------------------------------------------------
    # Internal – recognition loop (runs in daemon thread)
    # ------------------------------------------------------------------

    def _recognition_loop(self, session: _LiveSession) -> None:
        config = CameraConfig(
            camera_id=f"attendance-{session.session_id}",
            name="Classroom Camera",
            source=0,
        )

        try:
            session.transport.connect(config)
        except Exception as exc:
            logger.error(f"Camera failed for session {session.session_id}: {exc}")
            self._broadcast(session, {
                "type": "attendance.error",
                "code": "CAMERA_UNAVAILABLE",
                "message": str(exc),
                "session_id": session.session_id,
            })
            return

        # Per-session recognition service with classroom-scoped known faces
        service = RecognitionService()
        service.load_known_faces(session.known_faces)

        cooldown = getattr(settings, "ATTENDANCE_COOLDOWN_SECONDS", _COOLDOWN_DEFAULT)
        confirm_threshold = settings.FACE_CONFIRM_FRAMES

        logger.info(
            f"Recognition loop started: session={session.session_id} "
            f"known_faces={len(session.known_faces)}"
        )

        try:
            while not session.stop_event.is_set():
                t0 = time.monotonic()

                try:
                    frame_obj = session.transport.read_frame()
                except Exception as exc:
                    logger.warning(f"Frame read error (session {session.session_id}): {exc}")
                    time.sleep(0.2)
                    continue

                if frame_obj is None:
                    time.sleep(0.01)
                    continue

                hits = service.identify_frame(frame_obj.frame)

                # Annotate frame and push to single-frame buffer for MJPEG stream
                try:
                    annotated = self._annotate_frame(frame_obj.frame, hits)
                    ok_enc, jpeg_buf = cv2.imencode(
                        ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70]
                    )
                    if ok_enc:
                        with session.latest_frame_lock:
                            session.latest_annotated_jpeg = jpeg_buf.tobytes()
                except Exception:
                    pass  # never crash the recognition loop over annotation

                now_mono = time.monotonic()
                now_iso = datetime.now(timezone.utc).isoformat()

                for hit in hits:
                    if hit.matched and hit.external_student_id is not None:
                        ext_id = hit.external_student_id
                        session.confirmation_counts[ext_id] = (
                            session.confirmation_counts.get(ext_id, 0) + 1
                        )
                        count = session.confirmation_counts[ext_id]

                        if count < confirm_threshold:
                            continue  # not yet confirmed

                        last = session.last_confirmed_at.get(ext_id, 0.0)
                        if now_mono - last < cooldown:
                            continue  # in cooldown window

                        session.last_confirmed_at[ext_id] = now_mono
                        already_present = ext_id in session.present_external_ids
                        session.present_external_ids.add(ext_id)

                        if not already_present:
                            # Persist to DB and broadcast
                            self._mark_present_in_db(
                                session.session_id,
                                hit.student_id,
                                hit.confidence,
                                is_late=session.is_late_capture,
                            )
                            self._broadcast(session, {
                                "type": "student.recognized",
                                "session_id": session.session_id,
                                "student_id": hit.external_student_id,
                                "student_name": hit.student_name,
                                "confidence": round(hit.confidence, 3),
                                "present_count": len(session.present_external_ids),
                                "total_students": session.total_students,
                                "timestamp": now_iso,
                            })
                            logger.debug(
                                f"Present: {hit.student_name} "
                                f"(conf={hit.confidence:.2f}, session={session.session_id})"
                            )
                    else:
                        # Unknown face – throttle to one event per 30 hits
                        session.unknown_hit_count += 1
                        if session.unknown_hit_count % 30 == 1:
                            self._broadcast(session, {
                                "type": "student.unknown",
                                "session_id": session.session_id,
                                "timestamp": now_iso,
                            })

                # Pace to target FPS
                elapsed = time.monotonic() - t0
                sleep_time = _FRAME_INTERVAL - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except Exception as exc:
            logger.error(f"Recognition loop crashed (session {session.session_id}): {exc}")
            self._broadcast(session, {
                "type": "attendance.error",
                "code": "RECOGNITION_FAILED",
                "message": str(exc),
                "session_id": session.session_id,
            })
        finally:
            try:
                session.transport.disconnect()
            except Exception:
                pass
            logger.info(f"Recognition loop exited: session={session.session_id}")

    # ------------------------------------------------------------------
    # Internal – DB helpers (synchronous, run in thread executor or thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_or_create_daily_session(class_id: int) -> tuple[int, bool, set[int]]:
        """Resolve the single attendance session for this class and Riyadh day."""
        from app.core.enums import SessionStatus
        from app.models.session import ClassSession

        db = SessionLocal()
        try:
            session = (
                db.query(ClassSession)
                .filter(
                    ClassSession.class_id == class_id,
                    ClassSession.attendance_date == school_today(),
                )
                .first()
            )
            if session is None:
                session = ClassSession(
                    class_id=class_id,
                    attendance_date=school_today(),
                    status=SessionStatus.ACTIVE.value,
                    started_at=school_now(),
                )
                db.add(session)
                db.flush()
                for student in db.query(Student).filter(
                    Student.class_id == class_id, Student.is_active.is_(True)
                ):
                    db.add(AttendanceRecord(
                        session_id=session.id,
                        student_id=student.id,
                        status=AttendanceStatus.ABSENT.value,
                    ))
                db.commit()
                db.refresh(session)

            present_ids = {
                student.external_student_id
                for record, student in db.query(AttendanceRecord, Student)
                .join(Student, Student.id == AttendanceRecord.student_id)
                .filter(
                    AttendanceRecord.session_id == session.id,
                    AttendanceRecord.status.in_([
                        AttendanceStatus.PRESENT.value,
                        AttendanceStatus.LATE.value,
                        AttendanceStatus.RETURNED.value,
                    ]),
                )
                .all()
            }
            return session.id, session.initial_roll_call_completed_at is not None, present_ids
        finally:
            db.close()

    @staticmethod
    def _complete_initial_roll_call(session_id: int) -> None:
        from app.models.session import ClassSession

        db = SessionLocal()
        try:
            session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
            if session and session.initial_roll_call_completed_at is None:
                session.initial_roll_call_completed_at = school_now()
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"_end_db_session failed: {exc}")
        finally:
            db.close()

    @staticmethod
    def _mark_present_in_db(
        session_id: int, student_id: int, confidence: float, *, is_late: bool
    ) -> None:
        db = SessionLocal()
        try:
            record = (
                db.query(AttendanceRecord)
                .filter(
                    AttendanceRecord.session_id == session_id,
                    AttendanceRecord.student_id == student_id,
                )
                .first()
            )
            if record is None:
                record = AttendanceRecord(
                    session_id=session_id,
                    student_id=student_id,
                    status=AttendanceStatus.ABSENT.value,
                )
                db.add(record)
                db.flush()

            if record.status == AttendanceStatus.ABSENT.value:
                now = school_now()
                record.status = AttendanceStatus.LATE.value if is_late else AttendanceStatus.PRESENT.value
                record.check_in_at = now
                record.recognition_confidence = confidence
                record.detection_count = (record.detection_count or 0) + 1
                if is_late:
                    session = db.get(ClassSession, session_id)
                    if session:
                        record.late_minutes = max(0, int((now - session.started_at).total_seconds() // 60))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"_mark_present_in_db failed: {exc}")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Internal – enrollment helpers (async)
    # ------------------------------------------------------------------

    async def _prepare_classroom_faces(
        self,
        class_id: int,
        students: list[dict[str, Any]],
    ) -> list[KnownFace]:
        """Load per-image face embeddings for all students in the classroom.

        Flow per student:
        1. Upsert student row in local DB.
        2. Query Supabase students_images for all reference images.
        3. For each image: use cached embedding if URL unchanged, else
           download → encode → persist to student_face_embeddings.
        4. Stale cached rows (URL changed) are deleted.
        5. Return one KnownFace per valid image per student.
        """
        sep = "=" * 60
        logger.info(f"\n{sep}")
        logger.info("[FACE-ENROLLMENT]")
        logger.info(f"Classroom: {class_id}")
        logger.info(f"Loading students... ({len(students)} students)")

        loop = asyncio.get_running_loop()
        known_faces: list[KnownFace] = []
        db = SessionLocal()

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http:
                for s in students:
                    ext_id: int = s["external_id"]
                    name: str = s["name"]
                    fallback_url: str | None = s.get("image_url")

                    logger.info(f"\nStudent {ext_id} ({name})")

                    # Upsert student in local DB
                    local = (
                        db.query(Student)
                        .filter(Student.external_student_id == ext_id)
                        .first()
                    )
                    if local is None:
                        local = Student(
                            external_student_id=ext_id,
                            name=name,
                            class_id=class_id,
                            is_active=True,
                        )
                        db.add(local)
                        db.flush()
                    else:
                        local.name = name
                        local.class_id = class_id
                        db.flush()

                    # Fetch reference images from Supabase students_images
                    supabase_images = await self._fetch_student_images(http, ext_id)

                    # Fallback: if Supabase unreachable / unconfigured, use the
                    # single image URL the frontend passed (primary only).
                    if not supabase_images and fallback_url:
                        supabase_images = [{"type": "primary", "image_url": fallback_url}]
                        logger.info(
                            f"  Supabase images unavailable – using frontend fallback"
                        )

                    logger.info(f"  Images found: {len(supabase_images)}")
                    for img in supabase_images:
                        logger.info(f"    {img['type']}: {img['image_url']}")

                    if not supabase_images:
                        logger.warning(
                            f"  [FACE-ENROLLMENT] Student {ext_id}: no images found – "
                            f"skipping enrollment"
                        )
                        continue

                    # Load existing cached embeddings for this student
                    cached_rows: dict[str, StudentFaceEmbedding] = {
                        row.image_type: row
                        for row in db.query(StudentFaceEmbedding).filter(
                            StudentFaceEmbedding.student_id == local.id
                        ).all()
                    }

                    # Build set of current valid types so stale rows can be pruned
                    current_types = {img["type"] for img in supabase_images}
                    for stale_type, stale_row in list(cached_rows.items()):
                        if stale_type not in current_types:
                            db.delete(stale_row)
                            del cached_rows[stale_type]
                            logger.info(f"  Deleted stale cache: {stale_type}")

                    student_emb_count = 0
                    for img_info in supabase_images:
                        image_type: str = img_info["type"]
                        image_url: str = img_info["image_url"]

                        cached = cached_rows.get(image_type)

                        if cached and cached.image_url == image_url:
                            # Use cached embedding
                            try:
                                emb_arr = np.array(
                                    json.loads(cached.embedding_json), dtype=np.float32
                                )
                                known_faces.append(
                                    KnownFace(
                                        student_id=local.id,
                                        external_student_id=ext_id,
                                        name=name,
                                        embedding=emb_arr,
                                        image_type=image_type,
                                    )
                                )
                                student_emb_count += 1
                                logger.debug(f"    {image_type}: loaded from cache")
                            except Exception as exc:
                                logger.warning(f"    {image_type}: cache parse error – {exc}")
                            continue

                        # Cache miss or URL changed – download and encode
                        try:
                            resp = await http.get(image_url)
                            resp.raise_for_status()
                            image_bytes = resp.content

                            embedding: list[float] | None = await loop.run_in_executor(
                                None, _sync_encode_face, image_bytes
                            )
                            if embedding is None:
                                logger.warning(
                                    f"  [FACE-ENROLLMENT] Student {ext_id} "
                                    f"{image_type}: No face detected – skipping"
                                )
                                continue

                            # Upsert cache row (replace if URL changed)
                            if cached:
                                cached.image_url = image_url
                                cached.embedding_json = json.dumps(embedding)
                                cached.updated_at = datetime.utcnow()
                            else:
                                new_row = StudentFaceEmbedding(
                                    student_id=local.id,
                                    external_student_id=ext_id,
                                    image_type=image_type,
                                    image_url=image_url,
                                    embedding_json=json.dumps(embedding),
                                )
                                db.add(new_row)

                            db.flush()

                            emb_arr = np.array(embedding, dtype=np.float32)
                            known_faces.append(
                                KnownFace(
                                    student_id=local.id,
                                    external_student_id=ext_id,
                                    name=name,
                                    embedding=emb_arr,
                                    image_type=image_type,
                                )
                            )
                            student_emb_count += 1
                            logger.info(
                                f"    {image_type}: new embedding computed & cached"
                            )
                        except Exception as exc:
                            logger.warning(
                                f"  [FACE-ENROLLMENT] Student {ext_id} "
                                f"{image_type}: ERROR – {exc}"
                            )

                    logger.info(f"  Embeddings loaded: {student_emb_count}")

            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"_prepare_classroom_faces failed: {exc}")
        finally:
            db.close()

        # A single portrait is too weak for unattended attendance. Keep its
        # cached embedding for the enrollment screen, but exclude it from the
        # automatic recognition session until the student has enough angles.
        reference_count: dict[int, int] = {}
        for face in known_faces:
            reference_count[face.external_student_id] = reference_count.get(face.external_student_id, 0) + 1
        eligible_ids = {
            student_id
            for student_id, count in reference_count.items()
            if count >= settings.FACE_MIN_REFERENCE_IMAGES
        }
        excluded_ids = set(reference_count) - eligible_ids
        if excluded_ids:
            logger.warning(
                "[FACE-ENROLLMENT] Excluding %s student(s) with fewer than %s reference images: %s",
                len(excluded_ids),
                settings.FACE_MIN_REFERENCE_IMAGES,
                sorted(excluded_ids),
            )
        known_faces = [face for face in known_faces if face.external_student_id in eligible_ids]

        logger.info(
            f"\n[FACE-ENROLLMENT] Total embeddings for classroom {class_id}: "
            f"{len(known_faces)} across {len(students)} students"
        )
        logger.info(sep)
        return known_faces

    async def _fetch_student_images(
        self, http: httpx.AsyncClient, external_student_id: int
    ) -> list[dict[str, str]]:
        """Query Supabase REST API for all reference images of a student.

        Returns a list of {"type": str, "image_url": str} dicts.
        Falls back to empty list when Supabase is not configured.
        """
        if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
            logger.debug(
                "SUPABASE_URL / SUPABASE_ANON_KEY not configured – "
                "skipping students_images lookup"
            )
            return []

        try:
            resp = await http.get(
                f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/students_images",
                params={
                    "student_id": f"eq.{external_student_id}",
                    "select": "type,image_url",
                },
                headers={
                    "apikey": settings.SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_ANON_KEY}",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            rows = resp.json()
            return [
                {"type": row["type"], "image_url": row["image_url"]}
                for row in rows
                if row.get("image_url") and row.get("type")
            ]
        except Exception as exc:
            logger.warning(
                f"Supabase students_images fetch failed for "
                f"student {external_student_id}: {exc}"
            )
            return []

    def get_debug_info(self, class_id: int) -> dict[str, Any]:
        """Return cached embedding stats for a classroom (for the debug endpoint)."""
        db = SessionLocal()
        try:
            students = (
                db.query(Student)
                .filter(Student.class_id == class_id, Student.is_active == True)
                .all()
            )
            student_infos = []
            for s in students:
                emb_rows = (
                    db.query(StudentFaceEmbedding)
                    .filter(StudentFaceEmbedding.student_id == s.id)
                    .all()
                )
                student_infos.append(
                    {
                        "student_id": s.external_student_id,
                        "local_id": s.id,
                        "name": s.name,
                        "images": len(emb_rows),
                        "embeddings": len(emb_rows),
                        "types": [e.image_type for e in emb_rows],
                        "automatic_attendance_eligible": len(emb_rows) >= settings.FACE_MIN_REFERENCE_IMAGES,
                    }
                )
            return {
                "classroom_id": class_id,
                "model": "face_recognition (dlib – 128-D ResNet embedding)",
                "threshold": settings.FACE_MATCH_TOLERANCE,
                "confirm_frames": settings.FACE_CONFIRM_FRAMES,
                "minimum_reference_images": settings.FACE_MIN_REFERENCE_IMAGES,
                "minimum_confidence": settings.FACE_MIN_CONFIDENCE,
                "minimum_margin": settings.FACE_MATCH_MIN_MARGIN,
                "students": student_infos,
            }
        finally:
            db.close()


# Module-level singleton
live_manager = AttendanceLiveManager()
