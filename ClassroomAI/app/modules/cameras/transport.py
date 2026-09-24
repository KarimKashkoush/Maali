from __future__ import annotations

import time

import cv2

from .exceptions import CameraConnectionError, CameraReadError
from .interfaces import CameraTransport
from .models import CameraConfig, CameraFrame, CameraHealth, CameraInfo


class OpenCvCameraTransport(CameraTransport):
    """Concrete transport for local webcam and future RTSP sources.

    This layer is the only place where OpenCV is used. The rest of the application
    depends on the transport abstraction, so switching the underlying source later
    only requires a different transport implementation.
    """

    def __init__(self) -> None:
        self._capture: cv2.VideoCapture | None = None
        self._config: CameraConfig | None = None
        self._health = CameraHealth(camera_id="")
        self._info = CameraInfo(camera_id="", name="", source=None)

    def connect(self, config: CameraConfig) -> None:
        self.disconnect()
        self._config = config
        self._capture = cv2.VideoCapture(0)
        if not self._capture.isOpened():
            self._capture.release()
            self._capture = None
            raise CameraConnectionError(f"Unable to open camera source: {config.source}")

        self._info = CameraInfo(
            camera_id=config.camera_id,
            name=config.name,
            source=config.source,
            status="connected",
            connected=True,
        )
        self._health = CameraHealth(camera_id=config.camera_id, status="connected")

    def disconnect(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._info.status = "idle"
        self._info.connected = False

    def open(self, config: CameraConfig) -> None:
        self.connect(config)

    def close(self) -> None:
        self.disconnect()

    def read_frame(self) -> CameraFrame | None:
        if self._capture is None:
            raise CameraReadError("Camera transport is not open")

        ok, frame = self._capture.read()
        if not ok or frame is None:
            self._health.last_error = "Unable to read frame from camera source"
            self._health.status = "failed"
            raise CameraReadError("Unable to read frame from camera source")

        self._health.last_error = None
        self._health.status = "connected"
        self._health.last_frame_time = time.time()
        return CameraFrame(camera_id=self._info.camera_id, frame=frame, sequence=self._health.reconnect_count)

    def is_connected(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    def get_health(self) -> CameraHealth:
        return self._health

    def get_info(self) -> CameraInfo:
        return self._info
