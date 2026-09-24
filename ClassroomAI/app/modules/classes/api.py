from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def classes_health():
    return {"status": "ok", "module": "classes"}
