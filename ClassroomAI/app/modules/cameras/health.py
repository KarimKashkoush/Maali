from __future__ import annotations

from .interfaces import CameraTransport
from .models import CameraHealth


class CameraHealthMonitor:
    """Simple health monitor wrapper around a transport implementation."""

    def __init__(self, transport: CameraTransport) -> None:
        self._transport = transport

    def get_health(self) -> CameraHealth:
        return self._transport.get_health()
