from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class CameraConfig:
    """Configuration for a single camera source.

    The transport implementation uses this configuration to open the current video source.
    The source can be a local camera index for Sprint 1 and later be replaced with an
    RTSP URL without changing the rest of the application.
    """

    camera_id: str
    name: str = "camera"
    source: str | int | None = 0
    fps_target: float = 10.0
    reconnect_attempts: int = 5
    reconnect_delay_seconds: float = 2.0
    timeout_seconds: float = 2.0
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.camera_id:
            raise ValueError("camera_id is required")


@dataclass(slots=True)
class CameraInfo:
    """Runtime metadata for a camera instance."""

    camera_id: str
    name: str
    source: str | int | None
    status: str = "idle"
    connected: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class CameraHealth:
    """Health metrics for a camera stream."""

    camera_id: str
    status: str = "idle"
    fps: float = 0.0
    latency_ms: float = 0.0
    last_frame_time: datetime | None = None
    reconnect_count: int = 0
    last_error: str | None = None


@dataclass(slots=True)
class CameraFrame:
    """Minimal frame envelope passed through the video pipeline."""

    camera_id: str
    frame: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sequence: int = 0
