import argparse
import json
import time
from pathlib import Path

import cv2
import requests


def save_and_show_frame(
    frame,
    out_path: Path,
    window_name: str = "Captured frame",
    show: bool = True,
):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)

    if show:
        cv2.imshow(window_name, frame)
        cv2.waitKey(0)  # wait until key press
        cv2.destroyAllWindows()




def main():
    parser = argparse.ArgumentParser(description="Capture one frame from webcam and send to Classroom AI")
    parser.add_argument("--session-id", type=int, required=True, help="Active session id")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000/api/v1/attendance/session/{session_id}/process-frame")

    parser.add_argument("--camera", type=int, default=0, help="Webcam index (0 usually)")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--save-frame", type=str, default="./uploads/captured_frame.jpg", help="Where to save captured image")
    parser.add_argument("--no-show", action="store_true", help="Do not open a window to preview the frame")
    args = parser.parse_args()


    endpoint = args.url.format(session_id=args.session_id)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit("Could not open webcam. Try --camera 1")

    # Warm up
    time.sleep(0.5)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise SystemExit("Failed to read frame from webcam")

    # Save + show preview
    save_path = Path(args.save_frame)
    save_and_show_frame(frame, save_path, show=(not args.no_show))

    # Encode frame as JPEG
    ok, buf = cv2.imencode(".jpg", frame)

    if not ok:
        raise SystemExit("Failed to encode frame")

    files = {
        "frame": ("frame.jpg", buf.tobytes(), "image/jpeg")
    }

    r = requests.post(endpoint, files=files, timeout=args.timeout)
    print("Status:", r.status_code)
    try:
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(r.text)

    if r.status_code >= 400:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

