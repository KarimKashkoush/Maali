from __future__ import annotations

import os
import signal
import sys
import time
from threading import Event

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.modules.cameras.interfaces import FrameConsumer
from app.modules.cameras.models import CameraConfig
from app.modules.cameras.stream_manager import CameraStreamManager
from app.modules.cameras.transport import OpenCvCameraTransport
from app.modules.cameras.worker import CameraWorker


class FrameCounter(FrameConsumer):
    def __init__(self) -> None:
        self.count = 0

    def consume(self, frame) -> None:
        self.count += 1


class CameraWorkerRunner:
    def __init__(self) -> None:
        self._stop_event = Event()
        self._transport = OpenCvCameraTransport()
        self._stream_manager = CameraStreamManager(self._transport)
        self._frame_counter = FrameCounter()
        self._worker = CameraWorker(self._stream_manager, self._frame_counter)
        self._config = CameraConfig(camera_id="dev-cam", name="Laptop Webcam", source=0)
        self._last_status_print = 0.0
        self._connected_state = False
        self._reconnect_state = False
        self._last_frame_time = time.time()

    def run(self) -> None:
        print("==================================")
        print("Camera Worker Started")

        self._worker.configure(self._config)
        self._worker.start()

        try:
            while not self._stop_event.is_set():
                time.sleep(0.1)
                now = time.time()
                connected = self._transport.is_connected()

                if connected and not self._connected_state:
                    print("Camera Connected")
                    self._connected_state = True
                    self._reconnect_state = False
                elif not connected and self._connected_state:
                    print("Camera Disconnected")
                    self._connected_state = False

                if self._worker.last_error is not None and not self._reconnect_state:
                    print("Reconnecting...")
                    self._reconnect_state = True
                    self._worker.last_error = None
                elif self._worker.last_error is None:
                    self._reconnect_state = False

                if now - self._last_status_print >= 1.0:
                    self._print_status(now)
                    self._last_status_print = now
        except KeyboardInterrupt:
            print("\nStopping worker...")
        finally:
            self._stop_event.set()
            self._worker.stop()
            self._stream_manager.stop(self._config.camera_id)
            self._transport.disconnect()
            print("Camera Disconnected")
            print("Worker Stopped")
            print("==================================")

    def _print_status(self, now: float) -> None:
        elapsed = max(now - self._last_frame_time, 1e-9)
        frames = self._frame_counter.count
        fps = frames / elapsed if elapsed > 0 else 0.0
        print(f"Frames: {frames}")
        print(f"FPS: {fps:.1f}")

        self._last_frame_time = now
        self._frame_counter.count = 0

    def stop(self) -> None:
        self._stop_event.set()


if __name__ == "__main__":
    runner = CameraWorkerRunner()

    def handle_sigint(signum, frame) -> None:  # noqa: ARG001
        runner.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        runner.run()
    except KeyboardInterrupt:
        runner.stop()
        sys.exit(0)
