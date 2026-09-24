from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SessionStatus
from app.database.base import Base


class ClassSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("class_id", "attendance_date", name="uq_daily_attendance_class_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_session_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    class_id: Mapped[int] = mapped_column(Integer, index=True)
    room_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    teacher_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    branch_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # One persisted attendance record per class and school day.  Old lesson
    # sessions may keep this null after migration.
    attendance_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    initial_roll_call_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.ACTIVE.value)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=datetime.utcnow
    )

    events: Mapped[list["SessionEvent"]] = relationship(back_populates="session")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(back_populates="session")
