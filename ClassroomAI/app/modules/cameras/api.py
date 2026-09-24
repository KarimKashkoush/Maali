from fastapi import APIRouter

from app.modules.cameras.service import CameraService

router = APIRouter()
service = CameraService()


@router.get("/health")
def cameras_health():
    return {"status": "ok", "module": "cameras"}
