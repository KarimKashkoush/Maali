from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def identity_health():
    return {"status": "ok", "module": "identity"}
