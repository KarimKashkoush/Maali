import json
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from app.modules.recognition.repository import KnownFace, RecognitionRepository
from app.modules.recognition.service import RecognitionService


class RecognitionRepositoryTests(unittest.TestCase):
    def _make_student(self, sid, ext_id, name, encoding_json):
        s = MagicMock()
        s.id = sid
        s.external_student_id = ext_id
        s.name = name
        s.face_encoding = encoding_json
        s.is_active = True
        return s

    def test_loads_single_embedding_format(self) -> None:
        repo = RecognitionRepository()
        emb = [0.1] * 128
        student = self._make_student(1, 100, "Alice", json.dumps([emb]))
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [student]
        result = repo.get_all_enrolled(db)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Alice")
        self.assertEqual(result[0].embedding.shape, (128,))

    def test_loads_multi_embedding_format_and_averages(self) -> None:
        repo = RecognitionRepository()
        emb1 = [0.0] * 128
        emb2 = [1.0] * 128
        student = self._make_student(2, 200, "Bob", json.dumps([emb1, emb2]))
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [student]
        result = repo.get_all_enrolled(db)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result[0].embedding[0]), 0.5, places=5)

    def test_skips_student_with_no_encoding(self) -> None:
        repo = RecognitionRepository()
        student = self._make_student(3, 300, "Carol", None)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [student]
        result = repo.get_all_enrolled(db)
        self.assertEqual(len(result), 0)


class RecognitionServiceTests(unittest.TestCase):
    def _make_service(self, known_faces: list[KnownFace]):
        repo = MagicMock(spec=RecognitionRepository)
        service = RecognitionService(repository=repo, tolerance=0.5)
        service._known_faces = known_faces
        return service

    def test_returns_empty_for_blank_frame(self) -> None:
        service = self._make_service([])
        with patch("app.modules.recognition.service.face_recognition.face_locations", return_value=[]):
            hits = service.identify_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertEqual(hits, [])

    def test_returns_unknown_when_no_known_faces(self) -> None:
        service = self._make_service([])
        fake_loc = (10, 100, 90, 20)
        fake_enc = np.random.rand(128).astype(np.float32)
        with patch("app.modules.recognition.service.face_recognition.face_locations", return_value=[fake_loc]), \
             patch("app.modules.recognition.service.face_recognition.face_encodings", return_value=[fake_enc]):
            hits = service.identify_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertEqual(len(hits), 1)
        self.assertFalse(hits[0].matched)

    def test_matches_registered_student(self) -> None:
        known_emb = np.ones(128, dtype=np.float32)
        known = KnownFace(student_id=1, external_student_id=42, name="Test", embedding=known_emb)
        service = self._make_service([known])

        fake_loc = (10, 100, 90, 20)
        # Use very similar encoding so distance < 0.5
        similar = known_emb + np.full(128, 0.001, dtype=np.float32)
        with patch("app.modules.recognition.service.face_recognition.face_locations", return_value=[fake_loc]), \
             patch("app.modules.recognition.service.face_recognition.face_encodings", return_value=[similar]), \
             patch("app.modules.recognition.service.face_recognition.face_distance", return_value=np.array([0.1])):
            hits = service.identify_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].matched)
        self.assertEqual(hits[0].student_name, "Test")
        self.assertEqual(hits[0].external_student_id, 42)

    def test_no_match_when_distance_exceeds_tolerance(self) -> None:
        known_emb = np.ones(128, dtype=np.float32)
        known = KnownFace(student_id=1, external_student_id=42, name="Test", embedding=known_emb)
        service = self._make_service([known])

        fake_loc = (10, 100, 90, 20)
        far_enc = np.zeros(128, dtype=np.float32)
        with patch("app.modules.recognition.service.face_recognition.face_locations", return_value=[fake_loc]), \
             patch("app.modules.recognition.service.face_recognition.face_encodings", return_value=[far_enc]), \
             patch("app.modules.recognition.service.face_recognition.face_distance", return_value=np.array([0.9])):
            hits = service.identify_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertFalse(hits[0].matched)
        self.assertIsNone(hits[0].student_name)

    def test_rejects_an_ambiguous_match_between_two_students(self) -> None:
        first = KnownFace(
            student_id=1, external_student_id=42, name="First", embedding=np.ones(128, dtype=np.float32)
        )
        second = KnownFace(
            student_id=2, external_student_id=43, name="Second", embedding=np.ones(128, dtype=np.float32)
        )
        service = self._make_service([first, second])
        fake_loc = (10, 100, 90, 20)
        with patch("app.modules.recognition.service.face_recognition.face_locations", return_value=[fake_loc]), \
             patch("app.modules.recognition.service.face_recognition.face_encodings", return_value=[np.ones(128)]), \
             patch("app.modules.recognition.service.face_recognition.face_distance", return_value=np.array([0.30, 0.34])):
            hits = service.identify_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertFalse(hits[0].matched)
        self.assertIsNone(hits[0].student_name)


if __name__ == "__main__":
    unittest.main()
