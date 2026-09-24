import unittest
from unittest.mock import patch

from app.modules.cameras.models import CameraConfig
from app.modules.cameras.transport import OpenCvCameraTransport


class FakeCapture:
    def __init__(self, source):
        self.source = source
        self.opened = True

    def isOpened(self):
        return self.opened

    def read(self):
        return True, b"frame"

    def release(self):
        self.opened = False


class CameraTransportTests(unittest.TestCase):
    def test_connect_disconnect_and_read_frame(self) -> None:
        with patch("app.modules.cameras.transport.cv2.VideoCapture", FakeCapture):
            transport = OpenCvCameraTransport()
            config = CameraConfig(camera_id="cam-1", name="Local webcam", source=0)

            transport.connect(config)
            self.assertTrue(transport.is_connected())

            frame = transport.read_frame()
            self.assertIsNotNone(frame)
            self.assertEqual(frame.camera_id, "cam-1")

            transport.disconnect()
            self.assertFalse(transport.is_connected())


if __name__ == "__main__":
    unittest.main()
