from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.modules.enrollment.schemas import (
    EnrollmentStartResponse,
    EnrollmentStatusResponse,
    EnrollmentStopResponse,
    PhotoEnrollmentResponse,
)
from app.modules.enrollment.service import EnrollmentService

router = APIRouter()
_service = EnrollmentService()


@router.post(
    "/{student_id}/enroll/start",
    response_model=EnrollmentStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start face enrollment for a student",
)
def enroll_start(student_id: int, db: Session = Depends(get_db)):
    try:
        return _service.start(student_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{student_id}/enroll/stop",
    response_model=EnrollmentStopResponse,
    summary="Stop an in-progress enrollment session",
)
def enroll_stop(student_id: int):
    try:
        return _service.stop(student_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{student_id}/enroll/status",
    response_model=EnrollmentStatusResponse,
    summary="Get the current enrollment status for a student",
)
def enroll_status(student_id: int):
    return _service.status(student_id)


@router.post(
    "/{student_id}/register-face",
    response_model=PhotoEnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a student face with full quality validation (blur, size, single-face)",
)
async def register_face(
    student_id: int,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await photo.read()
    try:
        return _service.register_face(
            student_id=student_id,
            image_bytes=content,
            filename=photo.filename or "photo.jpg",
            db=db,
        )
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in msg.lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=msg) from exc


@router.post(
    "/{student_id}/photo",
    response_model=PhotoEnrollmentResponse,
    summary="Enroll a student from a single uploaded photo",
)
async def enroll_from_photo(
    student_id: int,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await photo.read()
    try:
        return _service.enroll_from_photo(
            student_id=student_id,
            image_bytes=content,
            filename=photo.filename or "photo.jpg",
            db=db,
        )
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in msg.lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=msg) from exc
