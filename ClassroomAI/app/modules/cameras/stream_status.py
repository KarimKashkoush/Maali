from __future__ import annotations

from enum import Enum


class StreamStatus(str, Enum):
    """State machine values for a camera stream."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    STOPPED = "stopped"
