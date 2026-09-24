from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def schools_health():
    return {"status": "ok", "module": "schools"}
