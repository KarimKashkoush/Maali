from __future__ import annotations

from abc import ABC, abstractmethod

from .models import CameraConfig, CameraFrame, CameraHealth, CameraInfo


class CameraTransport(ABC):
    """Abstract transport responsible for opening and reading from a video source."""

    @abstractmethod
    def connect(self, config: CameraConfig) -> None:
        """Open the configured video source."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the active video source."""

    @abstractmethod
    def open(self, config: CameraConfig) -> None:
        """Backward-compatible alias for connect."""

    @abstractmethod
    def close(self) -> None:
        """Backward-compatible alias for disconnect."""

    @abstractmethod
    def read_frame(self) -> CameraFrame | None:
        """Read a single frame from the source."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True when the source is connected and readable."""

    @abstractmethod
    def get_health(self) -> CameraHealth:
        """Return runtime health information."""

    @abstractmethod
    def get_info(self) -> CameraInfo:
        """Return metadata about the transport."""


class CameraStreamManagerProtocol(ABC):
    """Protocol-like abstraction for the stream manager behavior."""

    @abstractmethod
    def start(self, config: CameraConfig) -> CameraInfo:
        """Start a stream for the provided configuration."""

    @abstractmethod
    def stop(self, camera_id: str) -> None:
        """Stop a running stream."""

    @abstractmethod
    def get_status(self, camera_id: str) -> CameraInfo:
        """Get the current status of a stream."""

    @abstractmethod
    def list_streams(self) -> list[CameraInfo]:
        """List all known streams."""


class FrameConsumer(ABC):
    """Optional consumer interface for frame processing pipelines."""

    @abstractmethod
    def consume(self, frame: CameraFrame) -> None:
        """Process a single frame."""
