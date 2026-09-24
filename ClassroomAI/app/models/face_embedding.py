from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class StudentFaceEmbedding(Base):
    """One row per (student, image_type) — stores the 128-D face embedding.

    Cache key: (student_id, image_type, image_url).
    When the image URL changes, a new row is inserted and the old one removed.
    """

    __tablename__ = "student_face_embeddings"
    __table_args__ = (
        UniqueConstraint("student_id", "image_type", name="uq_student_image_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"), index=True)
    external_student_id: Mapped[int] = mapped_column(Integer, index=True)
    image_type: Mapped[str] = mapped_column(String(20))  # primary/front/left/right/up/down
    image_url: Mapped[str] = mapped_column(String(1000))
    embedding_json: Mapped[str] = mapped_column(Text)  # JSON array of 128 floats
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=datetime.utcnow
    )
