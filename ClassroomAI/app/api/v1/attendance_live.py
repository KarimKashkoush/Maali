"""Live attendance API: start/stop endpoints and WebSocket for real-time events."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Literal

from fastapi import APIRouter, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.modules.attendance.live_manager import live_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class StudentInput(BaseModel):
    external_id: int
    name: str
    image_url: str | None = None


class LiveStartRequest(BaseModel):
    class_id: int
    students: list[StudentInput]
    camera_mode: Literal["browser", "server"] = "browser"


class LiveStartResponse(BaseModel):
    session_id: int
    status: str
    total_students: int
    enrolled_students: int


class LiveStopResponse(BaseModel):
    status: str
    session_id: int
    present_count: int
    absent_count: int


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/live/start",
    response_model=LiveStartResponse,
    summary="Start live attendance: camera opens, recognition begins, use WS for events",
)
async def start_live_attendance(payload: LiveStartRequest) -> LiveStartResponse:
    result = await live_manager.start_session(
        class_id=payload.class_id,
        students=[s.model_dump() for s in payload.students],
        camera_mode=payload.camera_mode,
    )
    return LiveStartResponse(**result)


@router.post("/live/frame/{session_id}")
async def process_browser_frame(session_id: int, frame: UploadFile = File(...)) -> dict[str, Any]:
    """Process one browser-camera frame without storing the source image."""
    image_bytes = await frame.read()
    if not image_bytes:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty frame uploaded")
    result = await run_in_threadpool(live_manager.process_browser_frame, session_id, image_bytes)
    if result is None:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active browser attendance session")
    return result


@router.post(
    "/live/stop/{session_id}",
    response_model=LiveStopResponse,
    summary="Stop live attendance: camera releases, final result returned",
)
def stop_live_attendance(session_id: int) -> LiveStopResponse:
    result = live_manager.stop_session(session_id)
    if result["status"] == "not_found":
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No live session found for session_id={session_id}",
        )
    return LiveStopResponse(**result)


@router.get(
    "/live/status/{session_id}",
    summary="Get current live attendance status",
)
def live_attendance_status(session_id: int) -> dict[str, Any]:
    info = live_manager.get_session_status(session_id)
    if info is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No live session for session_id={session_id}",
        )
    return info


# ---------------------------------------------------------------------------
# MJPEG video stream endpoint
# ---------------------------------------------------------------------------

_MJPEG_BOUNDARY = b"frame"
_MJPEG_FRAME_INTERVAL = 0.1  # ~10 FPS


async def _mjpeg_generator(
    session_id: int, request: Request
) -> AsyncGenerator[bytes, None]:
    """Yield MJPEG frames from the shared annotated-frame buffer."""
    while True:
        if await request.is_disconnected():
            break

        if not live_manager.is_session_active(session_id):
            break

        jpeg = live_manager.get_latest_jpeg(session_id)
        if jpeg:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )

        await asyncio.sleep(_MJPEG_FRAME_INTERVAL)


@router.get(
    "/live/stream/{session_id}",
    summary="MJPEG live video stream for an active attendance session",
    response_class=StreamingResponse,
)
async def attendance_stream(session_id: int, request: Request) -> StreamingResponse:
    """Stream the annotated camera feed as MJPEG.

    The frames are taken from the shared single-frame buffer written by the
    recognition loop – no second camera capture is created.
    """
    if not live_manager.is_session_active(session_id):
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No active session for session_id={session_id}",
        )

    return StreamingResponse(
        _mjpeg_generator(session_id, request),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store"},
    )


# ---------------------------------------------------------------------------
# Debug / verification endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/live/debug/classroom/{classroom_id}",
    summary="Verify face embeddings cached for a classroom",
)
def debug_classroom_embeddings(classroom_id: int) -> dict[str, Any]:
    """Return the number of cached face embeddings per student for a classroom.

    Useful for confirming that students_images were downloaded and encoded
    correctly before starting a live attendance session.

    Example response::

        {
          "classroom_id": 1,
          "model": "face_recognition (dlib – 128-D ResNet embedding)",
          "threshold": 0.5,
          "students": [
            {
              "student_id": 19,
              "name": "أحمد",
              "images": 6,
              "embeddings": 6,
              "types": ["primary","front","left","right","up","down"]
            }
          ]
        }
    """
    return live_manager.get_debug_info(classroom_id)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/live/ws/{session_id}")
async def attendance_websocket(websocket: WebSocket, session_id: int) -> None:
    """WebSocket for real-time attendance events.

    Event types sent to the client
    --------------------------------
    attendance.started   – sent immediately after connect
    student.recognized   – a student was confirmed present
    student.unknown      – an unrecognised face was detected
    attendance.completed – session ended (sent after POST /live/stop)
    attendance.error     – camera or recognition failure
    """
    await websocket.accept()

    queue = live_manager.subscribe_client(session_id)
    if queue is None:
        await websocket.send_json({
            "type": "attendance.error",
            "code": "SESSION_NOT_FOUND",
            "message": f"No live session for session_id={session_id}",
            "session_id": session_id,
        })
        await websocket.close(code=1008)
        return

    # Send initial state to this client
    info = live_manager.get_session_status(session_id)
    if info:
        await websocket.send_json({"type": "attendance.started", **info})

    async def _send_loop() -> None:
        """Read from queue and forward to WebSocket until sentinel None."""
        while True:
            event = await queue.get()
            if event is None:
                break
            try:
                await websocket.send_json(event)
            except Exception:
                break

    async def _receive_loop() -> None:
        """Drain incoming WebSocket messages (ping/pong / client close)."""
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break

    send_task = asyncio.create_task(_send_loop())
    recv_task = asyncio.create_task(_receive_loop())

    try:
        done, pending = await asyncio.wait(
            {send_task, recv_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        live_manager.unsubscribe_client(session_id, queue)
        logger.debug(f"WebSocket client disconnected: session={session_id}")
