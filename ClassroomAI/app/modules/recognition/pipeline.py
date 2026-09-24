from __future__ import annotations

import threading
import time

import numpy as np

from app.database.connection import SessionLocal
from app.modules.cameras.models import CameraConfig
from app.modules.cameras.stream_manager import CameraStreamManager
from app.modules.cameras.transport import OpenCvCameraTransport
from app.modules.recognition.schemas import FaceHit, PipelineStatus
from app.modules.recognition.service import RecognitionService

_FACE_RELOAD_INTERVAL = 30.0   # seconds between database reloads
_FRAME_INTERVAL       = 0.033  # ~30 fps processing ceiling


class RecognitionPipeline:
    """Orchestrates the production face recognition loop.

    Architecture:
        CameraTransport (OpenCV, isolated)
            ↓
        CameraStreamManager (lifecycle management)
            ↓
        RecognitionService (face detection + matching)
            ↓
        RecognitionRepository (database reads)

    The pipeline runs on a background daemon thread.  The dev tool (and any
    future WebSocket/HTTP endpoint) consumes results via get_latest() which
    is fully thread-safe and never blocks the camera loop.
    """

    def __init__(
        self,
        transport: OpenCvCameraTransport,
        service: RecognitionService,
        reload_interval: float = _FACE_RELOAD_INTERVAL,
    ) -> None:
        self._transport      = transport
        self._stream_manager = CameraStreamManager(transport)
        self._service        = service
        self._reload_interval = reload_interval

        self._stop_event = threading.Event()
        self._status     = PipelineStatus.IDLE
        self._thread: threading.Thread | None = None

        self._frames_processed = 0
        self._last_error: str | None = None
        self._latest_frame: np.ndarray | None = None
        self._latest_hits: list[FaceHit] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, config: CameraConfig) -> None:
        """Start the recognition loop.  Safe to call multiple times."""
        with self._lock:
            if self._status == PipelineStatus.RUNNING:
                return
            self._stop_event.clear()
            self._status = PipelineStatus.RUNNING
            self._frames_processed = 0
            self._last_error = None

        self._thread = threading.Thread(
            target=self._loop,
            args=(config,),
            daemon=True,
            name="recognition-pipeline",
        )
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self._status not in (PipelineStatus.RUNNING, PipelineStatus.STOPPING):
                return
            self._status = PipelineStatus.STOPPING
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def get_latest(self) -> tuple[np.ndarray | None, list[FaceHit]]:
        """Thread-safe snapshot of the most recent frame and recognition hits."""
        with self._lock:
            frame = self._latest_frame.copy() if self._latest_frame is not None else None
            hits  = list(self._latest_hits)
        return frame, hits

    def get_status(self) -> dict:
        with self._lock:
            return {
                "status":           self._status.value,
                "frames_processed": self._frames_processed,
                "last_error":       self._last_error,
            }

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _loop(self, config: CameraConfig) -> None:
        try:
            self._stream_manager.start(config)
        except Exception as exc:
            with self._lock:
                self._status    = PipelineStatus.FAILED
                self._last_error = str(exc)
            return

        last_reload = 0.0

        try:
            while not self._stop_event.is_set():
                now = time.monotonic()

                # Periodic DB reload — uses its own short-lived session
                if now - last_reload >= self._reload_interval:
                    self._reload_faces()
                    last_reload = now

                try:
                    frame_obj = self._stream_manager.read_frame(config.camera_id)
                except Exception as exc:
                    with self._lock:
                        self._last_error = str(exc)
                    time.sleep(0.1)
                    continue

                if frame_obj is None:
                    time.sleep(0.01)
                    continue

                hits = self._service.identify_frame(frame_obj.frame)

                with self._lock:
                    self._latest_frame = frame_obj.frame.copy()
                    self._latest_hits  = hits
                    self._frames_processed += 1

                time.sleep(_FRAME_INTERVAL)

        except Exception as exc:
            with self._lock:
                self._status    = PipelineStatus.FAILED
                self._last_error = str(exc)
        finally:
            try:
                self._stream_manager.stop(config.camera_id)
            except Exception:
                pass
            with self._lock:
                if self._status not in (PipelineStatus.FAILED,):
                    self._status = PipelineStatus.STOPPED

    def _reload_faces(self) -> None:
        db = SessionLocal()
        try:
            count = self._service.reload_known_faces(db)
        except Exception as exc:
            with self._lock:
                self._last_error = f"DB reload error: {exc}"
        else:
            with self._lock:
                self._last_error = None
            print(f"[RecognitionPipeline] Known faces reloaded: {count}")
        finally:
            db.close()
