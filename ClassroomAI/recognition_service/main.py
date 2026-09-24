"""Run with: python -m uvicorn recognition_service.main:app --port 8001.

The service has no database access and never makes attendance decisions.
"""
from __future__ import annotations

import json
import math
import os
import secrets
import warnings
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Callable

import anyio
import face_recognition
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.datastructures import Headers, UploadFile
from starlette.responses import JSONResponse


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_CANDIDATES_JSON = 2 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + MAX_CANDIDATES_JSON + 64 * 1024
MAX_CANDIDATES = 100
MAX_SAMPLES = 6
MAX_FRAME_FACES = 100
MAX_PROCESSING_SIDE = 1920
MIN_FACE_SIDE = 50
MATCH_THRESHOLD = 0.42
MATCH_MARGIN = 0.08
MODEL = "dlib-v1"


@asynccontextmanager
async def lifespan(application: FastAPI):
    key = os.environ.get("RECOGNITION_API_KEY", "")
    if not key or not key.strip():
        raise RuntimeError("RECOGNITION_API_KEY is required; generate a random secret before starting.")
    application.state.api_key = key.encode("utf-8")
    # Shared dlib models execute serially; allow just one additional queued job.
    application.state.cpu_limiter = anyio.CapacityLimiter(1)
    application.state.inflight = 0
    yield
    application.state.api_key = b""


app = FastAPI(title="Classroom recognition worker", version="1.0.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


class InternalRequestGuard:
    """Authenticate before multipart parsing and bound total streamed input."""

    def __init__(self, app, key_getter: Callable[[], bytes]):
        self.app = app
        self.key_getter = key_getter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/internal/"):
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        supplied = headers.getlist("x-recognition-key")
        expected = self.key_getter()
        if not expected or len(supplied) != 1 or not secrets.compare_digest(
            supplied[0].encode("utf-8"), expected
        ):
            return await JSONResponse({"detail": "Unauthorized"}, status_code=401)(scope, receive, send)
        lengths = headers.getlist("content-length")
        try:
            declared = int(lengths[0]) if lengths else 0
            if len(lengths) > 1 or declared < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
        if declared > MAX_REQUEST_BYTES:
            return await JSONResponse({"detail": "Request exceeds size limit"}, status_code=413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_BYTES:
                    raise HTTPException(413, "Request exceeds size limit")
            return message

        return await self.app(scope, bounded_receive, send)


app.add_middleware(InternalRequestGuard, key_getter=lambda: getattr(app.state, "api_key", b""))


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL}


async def read_image(upload: UploadFile) -> bytes:
    """Do not trust the supplied filename, MIME type, or Content-Length."""
    try:
        data = await upload.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image must be at most 5 MiB")
        if not data:
            raise HTTPException(422, "Image is empty")
        return data
    finally:
        await upload.close()


def decode_image(data: bytes) -> tuple[np.ndarray, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(415, "Only JPEG, PNG and WebP images are supported")
                if source.width * source.height > MAX_PIXELS:
                    raise HTTPException(413, "Image must contain at most 16 million pixels")
                if getattr(source, "n_frames", 1) != 1:
                    raise HTTPException(422, "Animated images are not supported")
                source.verify()
            # verify() invalidates the decoder; reopen and decode all pixels.
            with Image.open(BytesIO(data)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source).convert("RGB")
                width, height = oriented.size
                oriented.thumbnail((MAX_PROCESSING_SIDE, MAX_PROCESSING_SIDE), Image.Resampling.LANCZOS)
                rgb = np.ascontiguousarray(np.asarray(oriented, dtype=np.uint8))
                return rgb, width, height
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(413, "Image exceeds the safe pixel limit") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(422, "Invalid or damaged image") from None


def parse_candidates(raw: str) -> list[tuple[int, list[list[float]]]]:
    if len(raw.encode("utf-8")) > MAX_CANDIDATES_JSON:
        raise HTTPException(413, "Candidate data exceeds size limit")
    try:
        def reject_nonfinite(value):
            raise ValueError("Non-finite JSON number")

        decoded = json.loads(raw, parse_constant=reject_nonfinite)
        if not isinstance(decoded, list) or len(decoded) > MAX_CANDIDATES:
            raise ValueError
        candidates = []
        identifiers = set()
        for candidate in decoded:
            if not isinstance(candidate, dict) or set(candidate) != {"student_id", "embeddings"}:
                raise ValueError
            student_id = candidate["student_id"]
            embeddings = candidate["embeddings"]
            if type(student_id) is not int or not 0 < student_id <= 9_007_199_254_740_991 or student_id in identifiers:
                raise ValueError
            if not isinstance(embeddings, list) or not 1 <= len(embeddings) <= MAX_SAMPLES:
                raise ValueError
            vectors = []
            for embedding in embeddings:
                if not isinstance(embedding, list) or len(embedding) != 128:
                    raise ValueError
                if any(type(value) not in (float, int) or not math.isfinite(value) for value in embedding):
                    raise ValueError
                vectors.append([float(value) for value in embedding])
            identifiers.add(student_id)
            candidates.append((student_id, vectors))
        return candidates
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise HTTPException(422, "Invalid candidates: use up to 100 unique positive student IDs, each with 1–6 finite 128-value embeddings") from None


def detect(rgb: np.ndarray):
    locations = face_recognition.face_locations(rgb, number_of_times_to_upsample=1, model="hog")
    # A bounded second pass helps locate smaller faces in HD inputs. Never
    # enlarge the identity crop or relax the minimum useful face size.
    if not locations and max(rgb.shape[:2]) <= 1280:
        locations = face_recognition.face_locations(rgb, number_of_times_to_upsample=2, model="hog")
    return locations


def encode(rgb: np.ndarray, locations):
    return face_recognition.face_encodings(rgb, known_face_locations=locations, num_jitters=1, model="small")


def valid_encoding(encoding) -> bool:
    return np.shape(encoding) == (128,) and bool(np.all(np.isfinite(encoding)))


def enroll_image(data: bytes):
    rgb, _, _ = decode_image(data)
    locations = detect(rgb)
    if len(locations) != 1:
        raise HTTPException(422, "Enrollment requires exactly one clearly visible face")
    top, right, bottom, left = locations[0]
    if min(bottom - top, right - left) < MIN_FACE_SIDE:
        raise HTTPException(422, "Face is too small; use a closer, clearer photo")
    encodings = encode(rgb, locations)
    if len(encodings) != 1 or not valid_encoding(encodings[0]):
        raise HTTPException(422, "Could not encode the face; use a clearer photo")
    return {"embedding": np.asarray(encodings[0], dtype=float).tolist(), "model": MODEL}


def match_encoding(encoding, candidates):
    if not candidates or not valid_encoding(encoding):
        return False, None, 0.0, None
    # The runner-up must be another student, not another sample of the winner.
    scores = sorted((min(math.dist(encoding, sample) for sample in samples), student_id)
                    for student_id, samples in candidates)
    distance, student_id = scores[0]
    if not math.isfinite(distance):
        return False, None, 0.0, None
    unambiguous = len(scores) == 1 or scores[1][0] - distance >= MATCH_MARGIN
    matched = distance <= MATCH_THRESHOLD and unambiguous
    # Similarity score, NOT a calibrated probability of identity.
    confidence = max(0.0, min(1.0, 1.0 - distance)) if matched else 0.0
    return matched, student_id if matched else None, round(confidence, 6), round(distance, 6)


def recognize_image(data: bytes, candidates):
    rgb, width, height = decode_image(data)
    locations = detect(rgb)
    if len(locations) > MAX_FRAME_FACES:
        raise HTTPException(422, "Too many faces; submit a smaller group")
    detections = []
    scale_x, scale_y = width / rgb.shape[1], height / rgb.shape[0]
    for location in locations:
        top, right, bottom, left = location
        reason = "face_too_small"
        match = (False, None, 0.0, None)
        if min(bottom - top, right - left) >= MIN_FACE_SIDE:
            reason = "no_clear_match"
            encodings = encode(rgb, [location])
            if len(encodings) == 1:
                match = match_encoding(encodings[0], candidates)
        matched, student_id, confidence, distance = match
        detections.append({
            "top": max(0, min(height, round(top * scale_y))),
            "right": max(0, min(width, round(right * scale_x))),
            "bottom": max(0, min(height, round(bottom * scale_y))),
            "left": max(0, min(width, round(left * scale_x))),
            "matched": matched, "student_id": student_id,
            "confidence": confidence, "distance": distance,
            "reason": None if matched else reason,
        })
    # Never assign the same student's identity to two faces in a single frame.
    ids = [item["student_id"] for item in detections if item["matched"]]
    duplicate_ids = {student_id for student_id in ids if ids.count(student_id) > 1}
    for item in detections:
        if item["student_id"] in duplicate_ids:
            item.update(matched=False, student_id=None, confidence=0.0, reason="duplicate_match")
    return {"frame_width": width, "frame_height": height, "detections": detections}


async def cpu_job(function, *args):
    if app.state.inflight >= 2:
        raise HTTPException(429, "Recognition worker is busy; retry shortly", headers={"Retry-After": "2"})
    app.state.inflight += 1
    try:
        return await anyio.to_thread.run_sync(function, *args, limiter=app.state.cpu_limiter)
    finally:
        app.state.inflight -= 1


@app.post("/internal/enroll")
async def enroll(request: Request):
    async with request.form(max_files=1, max_fields=0, max_part_size=MAX_CANDIDATES_JSON) as form:
        photo = form.get("photo")
        if list(form.keys()) != ["photo"] or not isinstance(photo, UploadFile):
            raise HTTPException(422, "Exactly one photo file is required")
        data = await read_image(photo)
    return await cpu_job(enroll_image, data)


@app.post("/internal/recognize")
async def recognize(request: Request):
    async with request.form(max_files=1, max_fields=1, max_part_size=MAX_CANDIDATES_JSON) as form:
        frame, raw = form.get("frame"), form.get("candidates")
        if set(form.keys()) != {"frame", "candidates"} or not isinstance(frame, UploadFile) or not isinstance(raw, str):
            raise HTTPException(422, "A frame file and candidates JSON field are required")
        parsed = parse_candidates(raw)
        data = await read_image(frame)
    return await cpu_job(recognize_image, data, parsed)
