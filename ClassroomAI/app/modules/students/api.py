from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.modules.students.service import StudentService
from app.schemas.student import StudentCreateRequest, StudentResponse, StudentSyncRequest

router = APIRouter()


@router.post("/sync", response_model=list[StudentResponse])
def sync_students(payload: StudentSyncRequest, db: Session = Depends(get_db)):
    return StudentService(db).sync_students(payload)


@router.post("", response_model=StudentResponse)
def create_student(payload: StudentCreateRequest, db: Session = Depends(get_db)):
    service = StudentService(db)
    student = service.upsert_student(payload)
    db.commit()
    return student


@router.get("", response_model=list[StudentResponse])
def list_students(class_id: int | None = None, db: Session = Depends(get_db)):
    return StudentService(db).list_students(class_id=class_id)


@router.get("/{external_student_id}", response_model=StudentResponse)
def get_student(external_student_id: int, db: Session = Depends(get_db)):
    return StudentService(db).get_student(external_student_id)


@router.post("/{external_student_id}/face", response_model=StudentResponse)
async def register_student_face(
    external_student_id: int,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return await StudentService(db).register_face(external_student_id, photo)
