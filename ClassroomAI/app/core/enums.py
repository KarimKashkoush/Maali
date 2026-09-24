from enum import StrEnum


class SessionStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class AttendanceStatus(StrEnum):
    ABSENT = "absent"
    PRESENT = "present"
    LATE = "late"
    LEFT = "left"
    RETURNED = "returned"


class EventType(StrEnum):
    STUDENT_IDENTIFIED = "student_identified"
    ATTENDANCE_MARKED = "attendance_marked"
    LATE_ARRIVAL = "late_arrival"
    LEFT_CLASS = "left_class"
    RETURNED = "returned"
    UNKNOWN_FACE = "unknown_face"


class ExportStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
