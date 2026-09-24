from __future__ import annotations

from threading import Lock

from .exceptions import CameraNotFoundError
from .interfaces import CameraStreamManagerProtocol, CameraTransport
from .models import CameraConfig, CameraFrame, CameraInfo
from .stream_status import StreamStatus


class CameraStreamManager(CameraStreamManagerProtocol):
    """Coordinates stream lifecycle for camera instances.

    The manager owns the decision to start, stop, and inspect streams while keeping
    the transport implementation behind the transport abstraction.
    """

    def __init__(self, transport: CameraTransport) -> None:
        self._transport = transport
        self._streams: dict[str, CameraInfo] = {}
        self._lock = Lock()

    def start(self, config: CameraConfig) -> CameraInfo:
        with self._lock:
            if config.camera_id in self._streams:
                return self._streams[config.camera_id]

            self._transport.connect(config)
            info = CameraInfo(
                camera_id=config.camera_id,
                name=config.name,
                source=config.source,
                status=StreamStatus.RUNNING.value,
                connected=self._transport.is_connected(),
            )
            self._streams[config.camera_id] = info
            return info

    def stop(self, camera_id: str) -> None:
        with self._lock:
            if camera_id not in self._streams:
                raise CameraNotFoundError(f"Camera stream '{camera_id}' was not found")
            self._transport.disconnect()
            self._streams[camera_id].status = StreamStatus.STOPPED.value
            self._streams[camera_id].connected = False

    def reconnect(self, config: CameraConfig) -> CameraInfo:
        with self._lock:
            self._transport.disconnect()
            self._transport.connect(config)
            info = self._streams.get(config.camera_id)
            if info is None:
                info = CameraInfo(
                    camera_id=config.camera_id,
                    name=config.name,
                    source=config.source,
                    status=StreamStatus.STARTING.value,
                    connected=self._transport.is_connected(),
                )
                self._streams[config.camera_id] = info
            info.status = StreamStatus.RUNNING.value
            info.connected = self._transport.is_connected()
            return info

    def read_frame(self, camera_id: str) -> CameraFrame | None:
        with self._lock:
            if camera_id not in self._streams:
                raise CameraNotFoundError(f"Camera stream '{camera_id}' was not found")
            return self._transport.read_frame()

    def update_state(self, camera_id: str, status: str, connected: bool, error: str | None = None) -> CameraInfo:
        with self._lock:
            if camera_id not in self._streams:
                raise CameraNotFoundError(f"Camera stream '{camera_id}' was not found")
            info = self._streams[camera_id]
            info.status = status
            info.connected = connected
            return info

    def get_status(self, camera_id: str) -> CameraInfo:
        with self._lock:
            if camera_id not in self._streams:
                raise CameraNotFoundError(f"Camera stream '{camera_id}' was not found")
            return self._streams[camera_id]

    def list_streams(self) -> list[CameraInfo]:
        with self._lock:
            return list(self._streams.values())
