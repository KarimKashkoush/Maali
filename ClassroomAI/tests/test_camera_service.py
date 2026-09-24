import unittest

from app.modules.cameras.models import CameraConfig, CameraHealth, CameraInfo
from app.modules.cameras.service import CameraService


class DummyTransport:
    def __init__(self):
        self.opened = []
        self.closed = False
        self.connected = False

    def connect(self, config: CameraConfig) -> None:
        self.opened.append(config)
        self.connected = True

    def disconnect(self) -> None:
        self.closed = True
        self.connected = False

    def open(self, config: CameraConfig) -> None:
        self.connect(config)

    def close(self) -> None:
        self.disconnect()

    def read_frame(self):
        return None

    def is_connected(self) -> bool:
        return self.connected

    def get_health(self) -> CameraHealth:
        return CameraHealth(camera_id="dummy")

    def get_info(self) -> CameraInfo:
        return CameraInfo(camera_id="dummy", name="dummy", source=None)


class CameraServiceTests(unittest.TestCase):
    def test_start_and_stop_streams(self) -> None:
        transport = DummyTransport()
        service = CameraService(transport=transport)
        config = CameraConfig(camera_id="cam-1", name="Test camera", source=0)

        info = service.start_stream(config)

        self.assertEqual(info.camera_id, "cam-1")
        self.assertTrue(transport.opened)
        self.assertEqual(service.get_stream_status("cam-1").status, "running")

        service.stop_stream("cam-1")
        self.assertEqual(service.get_stream_status("cam-1").status, "stopped")


if __name__ == "__main__":
    unittest.main()
