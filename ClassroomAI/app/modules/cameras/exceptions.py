class CameraError(Exception):
    """Base exception for camera-related failures."""


class CameraConnectionError(CameraError):
    """Raised when the configured source cannot be opened."""


class CameraReadError(CameraError):
    """Raised when a frame cannot be read from the active source."""


class CameraNotFoundError(CameraError):
    """Raised when a requested camera stream is unknown."""
