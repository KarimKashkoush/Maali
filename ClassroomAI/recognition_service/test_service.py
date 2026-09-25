"""Contract/security tests: real image parsing, mocks only for face inference."""
import asyncio
import json
import os
import threading
from io import BytesIO

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from recognition_service import main as service


KEY = "local-test-key-only-not-a-deployment-secret"
HEADERS = {"X-Recognition-Key": KEY}
BOX = (10, 100, 100, 10)


def image_bytes(fmt="PNG", size=(160, 120), **kwargs):
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format=fmt, **kwargs)
    return output.getvalue()


def sample(student_id=1, distance=0.0, count=1):
    return {"student_id": student_id, "embeddings": [[distance] + [0.0] * 127 for _ in range(count)]}


def recognize(client, candidates=None, data=None, **kwargs):
    return client.post("/internal/recognize", headers=HEADERS,
                       files={"frame": ("frame.png", data or image_bytes(), "image/png")},
                       data={"candidates": json.dumps(candidates if candidates is not None else [sample()])}, **kwargs)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RECOGNITION_API_KEY", KEY)
    with TestClient(service.app) as active:
        yield active


@pytest.fixture
def single_face(monkeypatch):
    monkeypatch.setattr(service, "detect", lambda rgb: [BOX])
    monkeypatch.setattr(service, "encode", lambda rgb, locations: [np.zeros(128) for _ in locations])


def test_missing_secret_prevents_startup(monkeypatch):
    monkeypatch.delenv("RECOGNITION_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="RECOGNITION_API_KEY"):
        with TestClient(service.app):
            pass


def test_health_and_auth_before_body_parsing(client):
    assert client.get("/health").json() == {"status": "ok", "model": "dlib-v1"}
    for headers in ({}, {"X-Recognition-Key": "wrong"}):
        result = client.post("/internal/enroll", content=b"invalid multipart", headers=headers)
        assert result.status_code == 401


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_enrollment_contract_and_true_format_detection(client, single_face, fmt):
    response = client.post("/internal/enroll", headers=HEADERS,
                           files={"photo": ("misleading.txt", image_bytes(fmt), "text/plain")})
    assert response.status_code == 200
    assert response.json() == {"embedding": [0.0] * 128, "model": "dlib-v1"}


@pytest.mark.parametrize("data,status", [(b"not an image", 422), (b"", 422),
                                        (b"x" * (service.MAX_IMAGE_BYTES + 1), 413)],
                         ids=["invalid-bytes", "empty", "oversize"])
def test_invalid_image_and_upload_size(client, data, status):
    response = client.post("/internal/enroll", headers=HEADERS,
                           files={"photo": ("photo.jpg", data, "image/jpeg")})
    assert response.status_code == status


def test_unsupported_real_format(client):
    result = client.post("/internal/enroll", headers=HEADERS,
                         files={"photo": ("fake.jpg", image_bytes("GIF"), "image/jpeg")})
    assert result.status_code == 415


def test_damaged_png(client):
    data = bytearray(image_bytes())
    data[-6] ^= 255
    result = client.post("/internal/enroll", headers=HEADERS,
                         files={"photo": ("photo.png", bytes(data), "image/png")})
    assert result.status_code == 422


def test_excessive_pixels_rejected_before_inference(client):
    result = client.post("/internal/enroll", headers=HEADERS,
                         files={"photo": ("photo.png", image_bytes(size=(4001, 4000)), "image/png")})
    assert result.status_code == 413


def test_animated_webp_rejected(client):
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="WEBP", save_all=True,
                                              append_images=[Image.new("RGB", (100, 100), "black")], duration=100)
    response = client.post("/internal/enroll", headers=HEADERS,
                           files={"photo": ("animated.webp", output.getvalue(), "image/webp")})
    assert response.status_code == 422


def test_request_size_and_chunked_body_limit(client):
    response = client.post("/internal/enroll", headers={**HEADERS, "Content-Length": str(service.MAX_REQUEST_BYTES + 1)}, content=b"x")
    assert response.status_code == 413
    body = b'--frame\r\nContent-Disposition: form-data; name="photo"; filename="x.png"\r\nContent-Type: image/png\r\n\r\n'
    chunks = [body, b"x" * service.MAX_REQUEST_BYTES, b"\r\n--frame--\r\n"]
    response = client.post("/internal/enroll", headers={**HEADERS, "Content-Type": "multipart/form-data; boundary=frame"},
                           content=iter(chunks))
    assert response.status_code == 413


@pytest.mark.parametrize("count", [0, 2])
def test_enrollment_requires_exactly_one_face(client, monkeypatch, count):
    monkeypatch.setattr(service, "detect", lambda rgb: [BOX] * count)
    response = client.post("/internal/enroll", headers=HEADERS, files={"photo": ("photo.png", image_bytes())})
    assert response.status_code == 422


def test_small_face_rejected_for_enrollment(client, monkeypatch):
    monkeypatch.setattr(service, "detect", lambda rgb: [(0, 20, 20, 0)])
    response = client.post("/internal/enroll", headers=HEADERS, files={"photo": ("photo.png", image_bytes())})
    assert response.status_code == 422


def test_recognition_contract(client, single_face):
    response = recognize(client, [sample(distance=0.2)])
    assert response.status_code == 200
    body = response.json()
    assert body.pop("processing_ms") >= 0
    assert body == {"frame_width": 160, "frame_height": 120, "detections": [
        {"top": 10, "right": 100, "bottom": 100, "left": 10, "matched": True,
         "student_id": 1, "confidence": 0.8, "distance": 0.2, "reason": None}]}


@pytest.mark.parametrize("candidates", [[], [sample(distance=0.421)], [sample(distance=0.2), sample(2, 0.21)]])
def test_unknown_or_ambiguous_faces_are_not_guessed(client, single_face, candidates):
    detection = recognize(client, candidates).json()["detections"][0]
    assert detection["matched"] is False
    assert detection["student_id"] is None
    assert detection["confidence"] == 0.0


def test_multiple_samples_same_student_are_not_ambiguous(client, single_face):
    detection = recognize(client, [sample(distance=0.2, count=6), sample(2, 0.5)]).json()["detections"][0]
    assert detection["student_id"] == 1


def test_match_threshold_boundary(client, single_face):
    result = recognize(client, [sample(distance=0.42)]).json()["detections"][0]
    assert result["matched"] is True
    assert result["confidence"] == 0.58


def test_duplicate_identity_in_one_frame_is_unknown(client, single_face, monkeypatch):
    monkeypatch.setattr(service, "detect", lambda rgb: [BOX, (15, 105, 105, 15)])
    detections = recognize(client).json()["detections"]
    assert len(detections) == 2
    assert all(not row["matched"] and row["student_id"] is None for row in detections)


def test_exif_orientation_and_scaled_boxes(client, single_face):
    exif = Image.Exif()
    exif[274] = 6
    body = recognize(client, data=image_bytes("JPEG", size=(2400, 1200), exif=exif)).json()
    assert (body["frame_width"], body["frame_height"]) == (1200, 2400)
    assert body["detections"][0]["top"] == 12
    assert body["detections"][0]["right"] == 125


@pytest.mark.parametrize("candidate_data", [
    {}, [sample(True)], [sample(0)], [sample("1")], [sample(), sample()],
    [{"student_id": 1, "embeddings": []}], [sample(count=7)],
    [{"student_id": 1, "embeddings": [[0.0] * 127]}],
    [{"student_id": 1, "embeddings": [[True] * 128]}],
    [{"student_id": 1, "embeddings": [["0"] * 128]}],
    [{"student_id": 1, "embeddings": [[float("nan")] * 128]}],
    [{"student_id": 1, "embeddings": [[float("inf")] * 128]}],
    [sample(i + 1) for i in range(101)],
])
def test_invalid_candidates(client, candidate_data):
    assert recognize(client, candidate_data).status_code == 422


def test_maximum_normal_candidates_exceeding_default_form_limit(client, single_face):
    candidates = [{"student_id": i + 1, "embeddings": [[0.12345678901234567] * 128 for _ in range(6)]} for i in range(100)]
    assert len(json.dumps(candidates)) > 1024 * 1024
    assert recognize(client, candidates).status_code == 200


def test_real_dlib_executes_on_empty_scene(client):
    # Neither detector nor encoder is replaced in this test.
    assert recognize(client, []).json()["detections"] == []
    response = client.post("/internal/enroll", headers=HEADERS, files={"photo": ("blank.png", image_bytes())})
    assert response.status_code == 422
    encodings = service.encode(np.zeros((120, 160, 3), dtype=np.uint8), [BOX])
    assert len(encodings) == 1 and service.valid_encoding(encodings[0])


def test_cpu_work_is_bounded_without_blocking_health(client, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow_detector(rgb):
        started.set()
        assert release.wait(timeout=5)
        return []

    monkeypatch.setattr(service, "detect", slow_detector)

    async def scenario():
        transport = httpx.ASGITransport(app=service.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            async def submit():
                return await http.post("/internal/recognize", headers=HEADERS,
                                       files={"frame": ("frame.png", image_bytes())}, data={"candidates": "[]"})
            first = asyncio.create_task(submit())
            await asyncio.to_thread(started.wait, 2)
            second = asyncio.create_task(submit())
            for _ in range(100):
                if service.app.state.inflight == 2:
                    break
                await asyncio.sleep(0.005)
            try:
                assert service.app.state.inflight == 2
                health = await asyncio.wait_for(http.get("/health"), timeout=0.5)
                assert health.status_code == 200
                overloaded = await submit()
                assert overloaded.status_code == 429
                assert overloaded.headers["retry-after"] == "2"
            finally:
                release.set()
                assert (await first).status_code == 200
                assert (await second).status_code == 200

    asyncio.run(scenario())


def test_hd_detection_retry_is_bounded(monkeypatch):
    calls = []
    def detector(rgb, number_of_times_to_upsample, model):
        calls.append(number_of_times_to_upsample)
        return [BOX] if number_of_times_to_upsample == 2 else []
    monkeypatch.setattr(service.face_recognition, "face_locations", detector)
    assert service.detect_for_enrollment(np.zeros((720, 1280, 3), dtype=np.uint8)) == [BOX]
    assert calls == [1, 2]
    calls.clear()
    assert service.detect_for_enrollment(np.zeros((1080, 1920, 3), dtype=np.uint8)) == []
    assert calls == [1]


def test_full_hd_pixels_are_preserved():
    rgb, width, height = service.decode_image(image_bytes(size=(1920, 1080)))
    assert rgb.shape == (1080, 1920, 3)
    assert (width, height) == (1920, 1080)


def test_small_face_reports_reason_without_matching(client, monkeypatch):
    monkeypatch.setattr(service, "detect", lambda rgb: [(0, 40, 40, 0)])
    def must_not_encode(*args):
        raise AssertionError("Small faces must not be used for identity")
    monkeypatch.setattr(service, "encode", must_not_encode)
    result = recognize(client).json()["detections"][0]
    assert result["reason"] == "face_too_small"
    assert result["matched"] is False and result["student_id"] is None


def test_live_detection_never_retries_empty_frame(monkeypatch):
    calls = []
    def detector(rgb, number_of_times_to_upsample, model):
        calls.append(number_of_times_to_upsample)
        return []
    monkeypatch.setattr(service.face_recognition, "face_locations", detector)
    assert service.detect(np.zeros((720, 1280, 3), dtype=np.uint8)) == []
    assert calls == [1]


def test_live_encodes_faces_in_one_batch(client, monkeypatch):
    boxes = [BOX, (10, 155, 100, 65)]
    monkeypatch.setattr(service, "detect", lambda rgb: boxes)
    calls = []
    def encoder(rgb, locations):
        calls.append(locations)
        return [np.zeros(128), np.ones(128)]
    monkeypatch.setattr(service, "encode", encoder)
    result = recognize(client).json()
    assert calls == [boxes]
    assert result["detections"][0]["student_id"] == 1
    assert result["detections"][1]["matched"] is False


def test_partial_encoder_result_does_not_assign_wrong_identity(client, monkeypatch):
    monkeypatch.setattr(service, "detect", lambda rgb: [BOX, (10, 155, 100, 65)])
    monkeypatch.setattr(service, "encode", lambda rgb, boxes: [np.zeros(128)])
    assert all(not d["matched"] for d in recognize(client).json()["detections"])
