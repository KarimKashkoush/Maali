from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def tracking_health():
    return {"status": "ok", "module": "tracking"}
