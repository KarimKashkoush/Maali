from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def behavior_health():
    return {"status": "ok", "module": "behavior"}
