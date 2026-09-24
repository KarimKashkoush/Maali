import argparse
import time

import cv2
import requests


def main():
    parser = argparse.ArgumentParser(description="Live webcam preview + send frames to Classroom AI")
    parser.add_argument("--session-id", type=int, required=True, help="Active session id")
    parser.add_argument(
        "--url",
        type=str,
        default="http://127.0.0.1:8000/api/v1/attendance/session/{session_id}/process-frame",
        help="process-frame endpoint",
    )
    parser.add_argument("--camera", type=int, default=0, help="Webcam index")
    parser.add_argument("--fps", type=float, default=2.0, help="How many frames to send per second")
    parser.add_argument("--jpeg-quality", type=int, default=90)
    parser.add_argument("--send", action="store_true", help="Actually send frames. If not set, only preview")
    parser.add_argument("--skip-n", type=int, default=0, help="Skip sending every N frames (0 = never skip)")
    args = parser.parse_args()

    endpoint = args.url.format(session_id=args.session_id)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit("Could not open webcam")

    last_sent = 0.0
    frame_idx = 0

    print("Controls: press 'q' to quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Local preview always
        view = frame.copy()

        now = time.time()
        should_send = (
            args.send
            and (now - last_sent) >= (1.0 / max(args.fps, 0.01))
            and (args.skip_n == 0 or (frame_idx % (args.skip_n + 1)) == 0)
        )

        overlay_text = None
        if should_send:
            last_sent = now

            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(args.jpeg_quality)]
            ok, buf = cv2.imencode(".jpg", frame, encode_param)
            if ok:
                files = {"frame": ("frame.jpg", buf.tobytes(), "image/jpeg")}
                try:
                    r = requests.post(endpoint, files=files, timeout=20)
                    if r.status_code == 200:
                        data = r.json()
                        # If any face is known -> assume match
                        known = any(i.get("is_known") for i in data.get("identifications", []))
                        overlay_text = "KNOWN (present)" if known else "UNKNOWN (not matched)"
                    else:
                        overlay_text = f"HTTP {r.status_code}"
                except Exception as e:
                    overlay_text = f"Error: {e}"[0:40]

        if overlay_text:
            cv2.putText(view, overlay_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.imshow("Live preview", view)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        frame_idx += 1

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

