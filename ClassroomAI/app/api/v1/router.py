from fastapi import APIRouter

from app.api.v1 import attendance, attendance_live, sessions, students
from app.modules.cameras.api import router as cameras_router
from app.modules.enrollment.api import router as enrollment_router
from app.modules.recognition.api import router as recognition_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(sessions.router, prefix="/sessions", tags=["Sessions"])
api_router.include_router(students.router, prefix="/students", tags=["Students"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
api_router.include_router(attendance_live.router, prefix="/attendance", tags=["Live Attendance"])
api_router.include_router(cameras_router, prefix="/cameras", tags=["Cameras"])
api_router.include_router(enrollment_router, prefix="/students", tags=["Enrollment"])
api_router.include_router(recognition_router, prefix="/recognition", tags=["Recognition"])
