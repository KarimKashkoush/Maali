import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from app.ai.face.face_extractor import (
    ExtractionResult,
    FaceEmbedding,
    FaceExtractor,
    RejectionReason,
)
from app.ai.face.face_recognition_service import FaceRecognitionService
from app.modules.enrollment.repository import EnrollmentRepository
from app.modules.enrollment.schemas import EnrollmentStatus
from app.modules.enrollment.service import EnrollmentService, _DUPLICATE_DISTANCE


class FaceExtractorTests(unittest.TestCase):
    def test_rejected_when_no_face(self) -> None:
        extractor = FaceExtractor()
        with patch("app.ai.face.face_extractor.face_recognition.face_locations", return_value=[]):
            result = extractor.extract(np.zeros((120, 120, 3), dtype=np.uint8))
        self.assertFalse(result.accepted)
        self.assertEqual(result.rejection_reason, RejectionReason.NO_FACE)

    def test_rejected_when_face_too_small(self) -> None:
        extractor = FaceExtractor(min_face_px=100)
        small_location = (0, 50, 50, 0)  # 50×50 — too small
        with patch("app.ai.face.face_extractor.face_recognition.face_locations", return_value=[small_location]):
            result = extractor.extract(np.zeros((120, 120, 3), dtype=np.uint8))
        self.assertFalse(result.accepted)
        self.assertEqual(result.rejection_reason, RejectionReason.TOO_SMALL)

    def test_rejected_when_blurry(self) -> None:
        extractor = FaceExtractor(blur_threshold=1e9, min_face_px=10)
        good_location = (0, 100, 100, 0)
        with patch("app.ai.face.face_extractor.face_recognition.face_locations", return_value=[good_location]):
            result = extractor.extract(np.zeros((120, 120, 3), dtype=np.uint8))
        self.assertFalse(result.accepted)
        self.assertEqual(result.rejection_reason, RejectionReason.BLURRY)

    def test_accepted_for_good_frame(self) -> None:
        extractor = FaceExtractor(blur_threshold=0.0, min_face_px=10)
        good_location = (0, 100, 100, 0)
        fake_encoding = np.random.rand(128)
        with patch("app.ai.face.face_extractor.face_recognition.face_locations", return_value=[good_location]), \
             patch("app.ai.face.face_extractor.face_recognition.face_encodings", return_value=[fake_encoding]):
            result = extractor.extract(np.zeros((120, 120, 3), dtype=np.uint8))
        self.assertTrue(result.accepted)
        self.assertIsNone(result.rejection_reason)
        self.assertIsInstance(result.embedding, FaceEmbedding)
        self.assertEqual(len(result.embedding.embedding), 128)


class DuplicateDetectionTests(unittest.TestCase):
    def test_no_duplicate_when_no_existing(self) -> None:
        emb = [0.1] * 128
        self.assertFalse(EnrollmentService._is_duplicate(emb, []))

    def test_no_duplicate_when_far_enough(self) -> None:
        existing = [[0.0] * 128]
        different = [1.0] * 128
        self.assertFalse(EnrollmentService._is_duplicate(different, existing))

    def test_detects_near_identical_embedding(self) -> None:
        base = np.ones(128, dtype=np.float32)
        tiny_noise = base + np.full(128, 0.001, dtype=np.float32)
        self.assertTrue(
            EnrollmentService._is_duplicate(tiny_noise.tolist(), [base.tolist()])
        )

    def test_validate_embeddings_removes_duplicates(self) -> None:
        base = np.ones(128, dtype=np.float32)
        near_clone = base + np.full(128, 0.001, dtype=np.float32)
        far = np.zeros(128, dtype=np.float32)
        result = EnrollmentService._validate_embeddings([
            base.tolist(),
            near_clone.tolist(),
            far.tolist(),
        ])
        self.assertEqual(len(result), 2)


class EnrollmentServiceTests(unittest.TestCase):
    def _make_service(self):
        repo = MagicMock(spec=EnrollmentRepository)
        extractor = MagicMock(spec=FaceExtractor)
        service = EnrollmentService(repository=repo, extractor=extractor)
        return service, repo, extractor

    def test_status_returns_idle_before_start(self) -> None:
        service, _, _ = self._make_service()
        result = service.status(student_id=42)
        self.assertEqual(result.status, EnrollmentStatus.IDLE)
        self.assertEqual(result.student_id, 42)
        self.assertEqual(result.samples_captured, 0)
        self.assertEqual(result.stats.accepted, 0)

    def test_stop_raises_when_no_session(self) -> None:
        service, _, _ = self._make_service()
        with self.assertRaises(ValueError):
            service.stop(student_id=99)

    def test_start_returns_running_and_stop_transitions_to_idle(self) -> None:
        service, repo, _ = self._make_service()
        mock_db = MagicMock()
        repo.find_student.return_value = MagicMock()  # student exists

        with patch("app.modules.enrollment.service.OpenCvCameraTransport"), \
             patch("app.modules.enrollment.service.CameraConfig"):
            response = service.start(student_id=1, db=mock_db)

        self.assertEqual(response.student_id, 1)
        self.assertEqual(response.status, EnrollmentStatus.RUNNING)

        stop_response = service.stop(student_id=1)
        self.assertIn(stop_response.status, (EnrollmentStatus.IDLE, EnrollmentStatus.COMPLETE))

    def test_stats_fields_present_in_response(self) -> None:
        service, repo, _ = self._make_service()
        mock_db = MagicMock()
        repo.find_student.return_value = MagicMock()

        with patch("app.modules.enrollment.service.OpenCvCameraTransport"), \
             patch("app.modules.enrollment.service.CameraConfig"):
            service.start(student_id=5, db=mock_db)

        resp = service.status(student_id=5)
        self.assertIsNotNone(resp.stats)
        self.assertGreaterEqual(resp.stats.rejected_blurry, 0)
        self.assertGreaterEqual(resp.stats.rejected_too_small, 0)
        self.assertGreaterEqual(resp.stats.rejected_no_face, 0)
        self.assertGreaterEqual(resp.stats.rejected_duplicate, 0)


class PhotoEnrollmentTests(unittest.TestCase):
    def _make_service(self, face_service_mock):
        repo = MagicMock(spec=EnrollmentRepository)
        extractor = MagicMock(spec=FaceExtractor)
        service = EnrollmentService(
            repository=repo,
            extractor=extractor,
            face_service=face_service_mock,
        )
        return service, repo

    def test_raises_when_student_not_found(self) -> None:
        face_svc = MagicMock(spec=FaceRecognitionService)
        service, repo = self._make_service(face_svc)
        repo.find_student.return_value = None

        with self.assertRaises(ValueError) as ctx:
            service.enroll_from_photo(99, b"bytes", "photo.jpg", MagicMock())
        self.assertIn("not found", str(ctx.exception).lower())

    def test_raises_when_no_face_detected(self) -> None:
        face_svc = MagicMock(spec=FaceRecognitionService)
        face_svc.encode_face_from_bytes.return_value = []
        service, repo = self._make_service(face_svc)
        repo.find_student.return_value = MagicMock()

        with self.assertRaises(ValueError) as ctx:
            service.enroll_from_photo(1, b"bytes", "photo.jpg", MagicMock())
        self.assertIn("no face", str(ctx.exception).lower())

    def test_raises_when_multiple_faces_detected(self) -> None:
        face_svc = MagicMock(spec=FaceRecognitionService)
        fake_enc = np.random.rand(128)
        face_svc.encode_face_from_bytes.return_value = [fake_enc, fake_enc]
        service, repo = self._make_service(face_svc)
        repo.find_student.return_value = MagicMock()

        with self.assertRaises(ValueError) as ctx:
            service.enroll_from_photo(1, b"bytes", "photo.jpg", MagicMock())
        self.assertIn("multiple faces", str(ctx.exception).lower())

    def test_saves_embedding_and_returns_success(self) -> None:
        face_svc = MagicMock(spec=FaceRecognitionService)
        fake_enc = np.random.rand(128)
        face_svc.encode_face_from_bytes.return_value = [fake_enc]
        service, repo = self._make_service(face_svc)
        repo.find_student.return_value = MagicMock()

        with patch.object(service, "_save_photo", return_value="/tmp/photo.jpg"):
            result = service.enroll_from_photo(1, b"bytes", "photo.jpg", MagicMock())

        self.assertTrue(result.success)
        self.assertTrue(result.face_detected)
        self.assertTrue(result.embedding_saved)
        self.assertEqual(result.student_id, 1)
        repo.save_photo_embedding.assert_called_once()


if __name__ == "__main__":
    unittest.main()
