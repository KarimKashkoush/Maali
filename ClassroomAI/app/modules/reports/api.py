from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def reports_health():
    return {"status": "ok", "module": "reports"}
