"""
Enroll & Recognize Demo
-----------------------
Standalone desktop debugging tool.

Pass a student photo on the command line and the camera opens immediately.
No form, no dialog — straight to the webcam.

Usage:
    # With a reference photo (shows name + confidence for matching faces):
    py -3 app/dev/enroll_and_recognize_demo.py --photo "C:/path/to/photo.jpg" --name "Kareem" --id 2

    # Without a photo (shows UNKNOWN for every face):
    py -3 app/dev/enroll_and_recognize_demo.py

Press Q to quit.
"""

from __future__ import annotations

import argparse
import os
import sys

import cv2
import face_recognition
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CAMERA_INDEX   = 0
TOLERANCE      = 0.50
DETECT_EVERY_N = 2
COLOR_MATCH    = (0, 200, 0)   # BGR green  — matched face
COLOR_UNKNOWN  = (0, 0, 220)   # BGR red    — unknown face
FONT           = cv2.FONT_HERSHEY_SIMPLEX


# ---------------------------------------------------------------------------
# Photo → embedding
# ---------------------------------------------------------------------------
def load_embedding(photo_path: str) -> np.ndarray:
    image = face_recognition.load_image_file(photo_path)
    locations = face_recognition.face_locations(image)

    if not locations:
        raise ValueError("No face detected in the selected photo.")
    if len(locations) > 1:
        raise ValueError(
            f"Multiple faces detected ({len(locations)}) in the photo. "
            "Use a photo with exactly one face."
        )

    return face_recognition.face_encodings(image, [locations[0]])[0]


# ---------------------------------------------------------------------------
# Live camera
# ---------------------------------------------------------------------------
def run_camera(name: str, sid: str, known_encoding: np.ndarray | None) -> None:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam.")
        return

    print("==================================")
    if known_encoding is not None:
        label = f"{name}" + (f"  (ID: {sid})" if sid else "")
        print(f"Enrolled:  {label}")
    else:
        print("Mode: detection only (no reference photo)")
    print("Camera opened — press Q to quit")
    print("==================================")

    frame_n = 0
    face_locs: list[tuple[int, int, int, int]] = []
    face_labels: list[tuple[bool, str]] = []

    while True:
        ok, frame_bgr = cap.read()
        if not ok or frame_bgr is None:
            continue

        frame_n += 1

        if frame_n % DETECT_EVERY_N == 0:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            face_locs = face_recognition.face_locations(rgb, model="hog")
            encodings = face_recognition.face_encodings(rgb, face_locs)

            face_labels = []
            for enc in encodings:
                if known_encoding is not None:
                    distance = float(face_recognition.face_distance([known_encoding], enc)[0])
                    if distance <= TOLERANCE:
                        confidence = int((1.0 - distance) * 100)
                        face_labels.append((True, f"{name}  {confidence}%"))
                    else:
                        face_labels.append((False, "UNKNOWN"))
                else:
                    face_labels.append((False, "UNKNOWN"))

        display = frame_bgr.copy()
        for (top, right, bottom, left), (matched, lbl) in zip(face_locs, face_labels):
            color = COLOR_MATCH if matched else COLOR_UNKNOWN
            cv2.rectangle(display, (left, top), (right, bottom), color, 2)
            cv2.putText(display, lbl, (left, max(top - 10, 18)), FONT, 0.65, color, 2, cv2.LINE_AA)

        if known_encoding is not None:
            cv2.putText(display, f"Enrolled: {name}", (10, 28), FONT, 0.60, (255, 255, 255), 2, cv2.LINE_AA)

        cv2.imshow("Enroll & Recognize Demo  |  Q to quit", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Camera released. Goodbye.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Enroll & Recognize Demo")
    parser.add_argument("--photo", default=None, help="Path to the student reference photo")
    parser.add_argument("--name",  default="Student", help="Student name shown on screen")
    parser.add_argument("--id",    default="",        help="Student ID (optional)")
    args = parser.parse_args()

    known_encoding: np.ndarray | None = None

    if args.photo:
        print(f"Loading embedding from: {args.photo}")
        try:
            known_encoding = load_embedding(args.photo)
            print("Embedding ready.")
        except ValueError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)

    run_camera(name=args.name, sid=args.id, known_encoding=known_encoding)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CAMERA_INDEX   = 0
TOLERANCE      = 0.50       # face distance threshold for a positive match
DETECT_EVERY_N = 2          # run detection every N frames for smooth display
COLOR_MATCH    = (0, 200, 0)    # BGR green  — matched face
COLOR_UNKNOWN  = (0, 0, 220)    # BGR red    — unknown face
FONT           = cv2.FONT_HERSHEY_SIMPLEX


# ---------------------------------------------------------------------------
# Enrollment form (tkinter)
# ---------------------------------------------------------------------------
class EnrollmentForm:
    """Simple tkinter form: name, ID, photo file selector."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Enroll Student")
        self.root.geometry("440x270")
        self.root.resizable(False, False)

        self._name    = tk.StringVar()
        self._sid     = tk.StringVar()
        self._photo   = tk.StringVar()
        self._ok      = False

        self._build()

    def _build(self) -> None:
        f = tk.Frame(self.root, padx=24, pady=24)
        f.pack(fill=tk.BOTH, expand=True)

        tk.Label(f, text="Student Name:", anchor="w").grid(row=0, column=0, sticky="w", pady=8)
        tk.Entry(f, textvariable=self._name, width=30).grid(row=0, column=1, sticky="w", pady=8)

        tk.Label(f, text="Student ID:", anchor="w").grid(row=1, column=0, sticky="w", pady=8)
        tk.Entry(f, textvariable=self._sid, width=30).grid(row=1, column=1, sticky="w", pady=8)

        tk.Label(f, text="Photo:", anchor="w").grid(row=2, column=0, sticky="w", pady=8)
        photo_row = tk.Frame(f)
        photo_row.grid(row=2, column=1, sticky="w")
        self._photo_lbl = tk.Label(photo_row, text="No file selected", fg="gray", width=22, anchor="w")
        self._photo_lbl.pack(side=tk.LEFT)
        tk.Button(photo_row, text="Browse…", command=self._browse).pack(side=tk.LEFT, padx=6)

        tk.Button(
            f, text="Start Camera ▶",
            command=self._submit,
            bg="#1b5e20", fg="white", width=22, pady=4,
        ).grid(row=3, column=0, columnspan=2, pady=20)

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Student Photo",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp"), ("All files", "*.*")],
        )
        if path:
            self._photo.set(path)
            self._photo_lbl.config(text=Path(path).name, fg="black")

    def _submit(self) -> None:
        if not self._name.get().strip():
            messagebox.showerror("Missing field", "Please enter a student name.")
            return
        if not self._photo.get().strip():
            messagebox.showerror("Missing field", "Please select a student photo.")
            return
        self._ok = True
        self.root.quit()

    def run(self) -> dict | None:
        self.root.mainloop()
        self.root.destroy()
        if not self._ok:
            return None
        return {
            "name":  self._name.get().strip(),
            "id":    self._sid.get().strip(),
            "photo": self._photo.get().strip(),
        }


# ---------------------------------------------------------------------------
# Photo → embedding
# ---------------------------------------------------------------------------
def load_embedding(photo_path: str) -> np.ndarray:
    """Load an image file and return the face encoding for the single face in it."""
    image = face_recognition.load_image_file(photo_path)
    locations = face_recognition.face_locations(image)

    if not locations:
        raise ValueError("No face detected in the selected photo.")
    if len(locations) > 1:
        raise ValueError(
            f"Multiple faces detected ({len(locations)}) in the selected photo.\n"
            "Please use a photo with exactly one face."
        )

    encodings = face_recognition.face_encodings(image, [locations[0]])
    return encodings[0]


# ---------------------------------------------------------------------------
# Live camera comparison
# ---------------------------------------------------------------------------
def run_camera(student: dict, known_encoding: np.ndarray) -> None:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam.")
        return

    display_name = f"{student['name']}"
    if student["id"]:
        display_name += f"  (ID: {student['id']})"

    print("==================================")
    print(f"Enrolled:  {display_name}")
    print("Camera opened — press Q to quit")
    print("==================================")

    frame_n      = 0
    face_locs: list[tuple[int, int, int, int]] = []
    face_labels: list[tuple[bool, str]] = []

    while True:
        ok, frame_bgr = cap.read()
        if not ok or frame_bgr is None:
            continue

        frame_n += 1

        if frame_n % DETECT_EVERY_N == 0:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            face_locs = face_recognition.face_locations(rgb, model="hog")
            encodings = face_recognition.face_encodings(rgb, face_locs)

            face_labels = []
            for enc in encodings:
                distance = float(face_recognition.face_distance([known_encoding], enc)[0])
                if distance <= TOLERANCE:
                    confidence = int((1.0 - distance) * 100)
                    face_labels.append((True, f"{student['name']}  {confidence}%"))
                else:
                    face_labels.append((False, "UNKNOWN"))

        display = frame_bgr.copy()

        for (top, right, bottom, left), (matched, label) in zip(face_locs, face_labels):
            color = COLOR_MATCH if matched else COLOR_UNKNOWN
            cv2.rectangle(display, (left, top), (right, bottom), color, 2)
            label_y = max(top - 10, 18)
            cv2.putText(display, label, (left, label_y), FONT, 0.65, color, 2, cv2.LINE_AA)

        # HUD — enrolled student name in top-left corner
        cv2.putText(
            display,
            f"Enrolled: {student['name']}",
            (10, 28), FONT, 0.60, (255, 255, 255), 2, cv2.LINE_AA,
        )

        cv2.imshow("Enroll & Recognize Demo  |  Q to quit", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Camera released. Goodbye.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    form = EnrollmentForm()
    student = form.run()

    if not student:
        print("Cancelled.")
        return

    print(f"\nStudent : {student['name']}  (ID: {student['id'] or '—'})")
    print(f"Photo   : {student['photo']}")
    print("Extracting face embedding…")

    try:
        known_encoding = load_embedding(student["photo"])
    except ValueError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Face Detection Error", str(exc))
        root.destroy()
        print(f"ERROR: {exc}")
        return

    print("Embedding ready — opening camera.")
    run_camera(student, known_encoding)


if __name__ == "__main__":
    main()
