from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.v1.router import api_router
from app.core.config import settings
from app.database.base import Base
from app.database.connection import engine
from app.models import (  # noqa: F401
    AttendanceRecord,
    ClassSession,
    ExportLog,
    SessionEvent,
    Student,
    StudentFaceEmbedding,
)
from app.schemas.common import HealthResponse, MessageResponse


def ensure_daily_attendance_schema() -> None:
    """Make existing SQLite installations compatible with daily attendance.

    Alembic remains the normal deployment path. This small startup guard keeps
    a development/school installation from failing with a 500 when it has an
    older SQLite file and the migration command was missed.
    """
    if engine.dialect.name != "sqlite":
        return
    columns = {column["name"] for column in inspect(engine).get_columns("sessions")}
    with engine.begin() as connection:
        if "attendance_date" not in columns:
            connection.execute(text("ALTER TABLE sessions ADD COLUMN attendance_date DATE"))
        if "initial_roll_call_completed_at" not in columns:
            connection.execute(text("ALTER TABLE sessions ADD COLUMN initial_roll_call_completed_at DATETIME"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_attendance_date ON sessions (attendance_date)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_attendance_class_date ON sessions (class_id, attendance_date)"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    ensure_daily_attendance_schema()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered Smart School Platform - MVP v1",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# The Next.js dashboard is served separately during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/", response_model=MessageResponse)
def root():
    return MessageResponse(message="Welcome to Classroom AI")


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
    )
