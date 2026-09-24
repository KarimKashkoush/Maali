from fastapi import APIRouter, HTTPException, status

from app.modules.cameras.models import CameraConfig
from app.modules.cameras.transport import OpenCvCameraTransport
from app.modules.recognition.pipeline import RecognitionPipeline
from app.modules.recognition.repository import RecognitionRepository
from app.modules.recognition.schemas import PipelineStatus, RecognitionStatusResponse
from app.modules.recognition.service import RecognitionService

router = APIRouter()

# Module-level singletons — one pipeline per application instance
_transport = OpenCvCameraTransport()
_service   = RecognitionService(RecognitionRepository())
_pipeline  = RecognitionPipeline(_transport, _service)

_DEFAULT_CONFIG = CameraConfig(
    camera_id="recognition",
    name="Webcam Recognition",
    source=0,
)


@router.post(
    "/start",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start the live face recognition pipeline",
)
def start_recognition():
    _pipeline.start(_DEFAULT_CONFIG)
    return {"status": "started"}


@router.post(
    "/stop",
    summary="Stop the live face recognition pipeline",
)
def stop_recognition():
    _pipeline.stop()
    return {"status": "stopped"}


@router.get(
    "/status",
    response_model=RecognitionStatusResponse,
    summary="Get recognition pipeline status and frame count",
)
def get_status():
    s = _pipeline.get_status()
    return RecognitionStatusResponse(
        status=PipelineStatus(s["status"]),
        frames_processed=s["frames_processed"],
        last_error=s["last_error"],
    )
