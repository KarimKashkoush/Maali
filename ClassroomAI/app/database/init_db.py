from app.database.connection import engine
from app.database.base import Base

from app.models import (  # noqa: F401
    AttendanceRecord,
    ClassSession,
    ExportLog,
    SessionEvent,
    Student,
)

Base.metadata.create_all(bind=engine)

print("Database created successfully")
