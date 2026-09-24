from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Classroom AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite:///./classroom_ai.db"

    # Supabase – used to fetch students_images for face enrollment
    SUPABASE_URL: str = "https://slhuekpyjdongbkoiuyg.supabase.co"          # e.g. https://xxxx.supabase.co
    SUPABASE_ANON_KEY: str = "sb_publishable_jYuJtKawwxRk1EYHOLEp6g_SWFIZC9C"     # public anon key (read-only for students_images)

    # Face recognition
    # Conservative defaults: a missed recognition can be corrected manually;
    # a false attendance record is much harder to recover from.
    FACE_MATCH_TOLERANCE: float = 0.42
    FACE_MIN_CONFIDENCE: float = 0.62
    # The nearest candidate must be clearly ahead of every *other student*,
    # preventing ambiguous matches from being auto-approved.
    FACE_MATCH_MIN_MARGIN: float = 0.08
    # A student needs several registered angles before automatic recognition.
    FACE_MIN_REFERENCE_IMAGES: int = 3
    FACE_CONFIRM_FRAMES: int = 5

    # Attendance
    LATE_GRACE_MINUTES: int = 10
    ABSENCE_TIMEOUT_MINUTES: int = 15
    # Seconds before the same student can trigger another recognized event
    ATTENDANCE_COOLDOWN_SECONDS: float = 30.0

    # School Platform integration
    SCHOOL_PLATFORM_WEBHOOK_URL: str = ""
    SCHOOL_PLATFORM_API_KEY: str = ""

    # Storage
    UPLOAD_DIR: str = "./uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: bool | str) -> bool | str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"development", "dev", "debug"}:
                return True
            if normalized in {"release", "production", "prod"}:
                return False
        return value


settings = Settings()
