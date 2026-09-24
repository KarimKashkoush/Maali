from __future__ import annotations

from .interfaces import CameraTransport
from .models import CameraConfig, CameraInfo
from .stream_manager import CameraStreamManager
from .stream_status import StreamStatus


class CameraService:
    """Application-facing service for camera stream lifecycle operations."""

    def __init__(self, db=None, transport: CameraTransport | None = None):
        self.db = db
        self._transport = transport
        self._stream_manager = CameraStreamManager(transport or self._build_default_transport())

    def _build_default_transport(self) -> CameraTransport:
        from .transport import OpenCvCameraTransport

        return OpenCvCameraTransport()

    def start_stream(self, config: CameraConfig) -> CameraInfo:
        return self._stream_manager.start(config)

    def stop_stream(self, camera_id: str) -> None:
        self._stream_manager.stop(camera_id)

    def get_stream_status(self, camera_id: str) -> CameraInfo:
        return self._stream_manager.get_status(camera_id)

    def list_streams(self) -> list[CameraInfo]:
        return self._stream_manager.list_streams()

    @property
    def stream_manager(self) -> CameraStreamManager:
        return self._stream_manager
