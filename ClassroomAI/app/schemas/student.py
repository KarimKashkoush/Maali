from pydantic import BaseModel, ConfigDict, Field


class StudentCreateRequest(BaseModel):
    external_student_id: int
    name: str = Field(min_length=1, max_length=255)
    class_id: int
    branch_id: int | None = None


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_student_id: int
    name: str
    class_id: int
    branch_id: int | None
    is_active: bool
    has_face_encoding: bool = False


class StudentSyncRequest(BaseModel):
    students: list[StudentCreateRequest]
