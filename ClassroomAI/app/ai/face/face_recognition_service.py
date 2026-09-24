import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import face_recognition
import numpy as np


@dataclass
class FaceMatch:
    student_id: int
    external_student_id: int
    student_name: str
    confidence: float
    distance: float


@dataclass
class UnknownFace:
    confidence: float = 0.0


class FaceRecognitionService:
    def encode_face_from_image(self, image_path: str | Path) -> list[float]:
        image = face_recognition.load_image_file(str(image_path))
        encodings = face_recognition.face_encodings(image)
        if not encodings:
            raise ValueError("No face detected in the image")
        if len(encodings) > 1:
            raise ValueError("Multiple faces detected. Please upload a photo with one face only")
        return encodings[0].tolist()

    def encode_face_from_bytes(self, image_bytes: bytes) -> list:
        image = face_recognition.load_image_file(BytesIO(image_bytes))
        encodings = face_recognition.face_encodings(image)
        if not encodings:
            raise ValueError("No face detected in the frame")
        return encodings

    @staticmethod
    def serialize_encoding(encoding: list[float]) -> str:
        return json.dumps(encoding)

    @staticmethod
    def deserialize_encoding(encoding_json: str) -> np.ndarray:
        return np.array(json.loads(encoding_json))

    def identify_faces(
        self,
        frame_encodings: list[np.ndarray],
        known_encodings: list[np.ndarray],
        known_metadata: list[tuple[int, int, str]],
        tolerance: float,
    ) -> list[FaceMatch | UnknownFace]:
        if not frame_encodings:
            return []

        if not known_encodings:
            return [UnknownFace() for _ in frame_encodings]

        results: list[FaceMatch | UnknownFace] = []
        for frame_encoding in frame_encodings:
            distances = face_recognition.face_distance(known_encodings, frame_encoding)
            best_index = int(np.argmin(distances))
            best_distance = float(distances[best_index])

            if best_distance <= tolerance:
                student_id, external_student_id, student_name = known_metadata[best_index]
                confidence = max(0.0, min(1.0, 1.0 - best_distance))
                results.append(
                    FaceMatch(
                        student_id=student_id,
                        external_student_id=external_student_id,
                        student_name=student_name,
                        confidence=confidence,
                        distance=best_distance,
                    )
                )
            else:
                results.append(UnknownFace(confidence=max(0.0, 1.0 - best_distance)))

        return results
