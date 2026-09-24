from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def teachers_health():
    return {"status": "ok", "module": "teachers"}
