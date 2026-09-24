# Python recognition worker

This stateless service only validates images, detects faces, creates 128-value dlib embeddings, and compares faces against the supplied candidates. Node.js owns authentication, schools, classrooms, student enrollment, private storage, attendance schedules, confirmation over multiple frames, and PostgreSQL. Python does not contact a database, download images, or decide attendance.

## Start locally

Run from the `ClassroomAI` directory with Python 3.11. The existing `.venv` already contains the face libraries on this development computer:

```powershell
.venv\Scripts\python.exe -m recognition_service.run --env-file ..\classroom_ai_backend\.env
```

The launcher reads only `RECOGNITION_API_KEY` from that file and does not modify it or expose its contents. It binds to `127.0.0.1:8001`. Alternatively, set `RECOGNITION_API_KEY` in the process environment and run `python -m recognition_service.run`. A missing or blank key fails startup. Generate a long random secret (at least 32 random bytes) and use the same value in Node. Do not put it in browser variables.

For a new environment, install `recognition_service/requirements.txt`. dlib requires a working C++ compiler and CMake when a suitable wheel is unavailable. The Docker image supplies those dependencies during its build. `setuptools` is pinned below the removal of `pkg_resources`, which the face model package still imports.

## Contract

`GET /health` is unauthenticated and returns `{"status":"ok","model":"dlib-v1"}`. All `/internal/*` requests require `X-Recognition-Key`; the header is compared in constant time before multipart parsing. These routes belong on a private network behind Node, not directly in the browser.

`POST /internal/enroll`: multipart field `photo`, exactly one file. Returns `{"embedding":[128 finite numbers],"model":"dlib-v1"}`. The photo must contain exactly one face at least 50 pixels wide and high after resizing.

`POST /internal/recognize`: multipart file `frame` plus text field `candidates` containing a JSON array:

```json
[{"student_id":1,"embeddings":[[0.01,0.02]]}]
```

The example vector is abbreviated: every embedding must have exactly 128 finite numeric values. Candidate IDs must be unique positive safe integers. Maximum 100 students, 1–6 embeddings each, and 2 MiB of candidate JSON. An empty array is allowed and produces unknown faces.

Response shape:

```json
{
  "frame_width": 1280,
  "frame_height": 720,
  "detections": [{
    "top": 80, "right": 300, "bottom": 280, "left": 100,
    "matched": true, "student_id": 1, "confidence": 0.8, "distance": 0.2
  }]
}
```

Coordinates refer to the decoded, EXIF-oriented frame at its original dimensions. Unknown detections have `matched:false`, `student_id:null`, `confidence:0`, and a nearest distance when available (otherwise `null`). No faces returns an empty detection array. Unknown faces never create a new student.

Errors use `{"detail":"..."}`: 401 for missing/wrong key; 413 for size limits; 415 for unsupported image formats; 422 for damaged images, unsuitable enrollment images, or invalid candidates; 429 with `Retry-After: 2` while the worker is overloaded. Malformed multipart input can return 400. Node should surface a clear retry/error message and must not record attendance on any error.

## Limits and matching

- Real JPEG, PNG and WebP files only; content is decoded independently of the MIME type or filename. Animation is rejected. Limit: 5 MiB per image, 16 million pixels before resizing. EXIF rotation is applied before recognition.
- Processing resizes the longest side to at most 1600 pixels. Very small, distant, blurred, or occluded faces may remain unknown. Rejects frames exceeding 100 detected faces.
- A match requires Euclidean distance at most `0.42` and at least `0.08` separation from the best sample of the next **different student**. Multiple pictures of one student do not cause false ambiguity. If two faces claim the same identity in a frame, both are returned as unknown.
- `confidence = 1 - distance` for accepted matches, rounded to six decimals. This is a similarity score, not a calibrated probability. Node may impose a stricter confidence gate; its 0.62 minimum means effective distance at most 0.38 before its multi-frame attendance confirmation.
- CPU work runs off the HTTP event loop, one job at a time, with one queued job. Extra work returns 429. Run one Uvicorn worker per CPU-service instance; multiple workers multiply model memory usage. The Docker command also bounds concurrent HTTP connections.

The upstream model is trained on adults and is less reliable on children; its maintainers explicitly document this limitation in [face_recognition's caveats](https://github.com/ageitgey/face_recognition#caveats). Conservative thresholds reduce accidental matches but do not eliminate them. Validate representative students, classroom lighting and camera distances before relying on automatic attendance. Retain teacher correction and a manual attendance path. This worker does not provide liveness or anti-spoofing detection; a photograph can resemble a live face.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest recognition_service\test_service.py -q -p no:cacheprovider
```

Tests exercise real image decoders, EXIF rotation, file/pixel limits, authentication, input validation, duplicate/ambiguous recognition and bounded concurrency. Contract tests replace face inference only. A separate test runs the installed dlib detector and encoder; this is a runtime check, not a real-world accuracy benchmark. No stored student photos are used by the tests.

## CPU container

Build with the repository root as context:

```sh
docker build -f recognition_service/Dockerfile -t classroom-recognition .
docker run --rm --env-file ../classroom_ai_backend/.env -p 127.0.0.1:8001:8001 classroom-recognition
```

Prefer passing only `RECOGNITION_API_KEY` from your deployment secret manager in production. The image runs as an unprivileged user, has a health check, and needs no GPU, volume, or public storage. Image bytes and vectors live only in request memory or temporary multipart files, closed after processing; they are not logged. Free hosting CPU/RAM and idle-sleep limits vary: do not assume a small free web tier can sustain live classroom recognition.
