from __future__ import annotations

import threading
import time

from .exceptions import CameraReadError
from .interfaces import FrameConsumer
from .models import CameraConfig
from .stream_manager import CameraStreamManager
from .stream_status import StreamStatus


class CameraWorker(threading.Thread):
    """Background worker that reads frames from the stream manager."""

    def __init__(self, stream_manager: CameraStreamManager, consumer: FrameConsumer | None = None) -> None:
        super().__init__(daemon=True)
        self._stream_manager = stream_manager
        self._consumer = consumer
        self._stop_event = threading.Event()
        self._config: CameraConfig | None = None
        self._last_error: Exception | None = None

    def configure(self, config: CameraConfig) -> None:
        self._config = config

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        if self._config is None:
            return

        self._stream_manager.start(self._config)
        while not self._stop_event.is_set():
            try:
                frame = self._stream_manager.read_frame(self._config.camera_id)
            except CameraReadError as exc:
                self._last_error = exc
                self._stream_manager.update_state(self._config.camera_id, StreamStatus.FAILED.value, False, str(exc))
                self._stream_manager.reconnect(self._config)
                time.sleep(0.5)
                continue
            except Exception as exc:  # pragma: no cover - defensive
                self._last_error = exc
                self._stream_manager.update_state(self._config.camera_id, StreamStatus.FAILED.value, False, str(exc))
                time.sleep(0.1)
                continue

            if frame is not None:
                self._stream_manager.update_state(self._config.camera_id, StreamStatus.RUNNING.value, True)
                if self._consumer is not None:
                    self._consumer.consume(frame)

            time.sleep(0.01)

    @property
    def last_error(self) -> Exception | None:
        return self._last_error
