"""School-day time helpers.

Attendance is reset by choosing a new Riyadh calendar date, not by deleting
records at midnight.  This keeps the history intact while every classroom
automatically starts with a fresh daily record after 00:00.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo


SCHOOL_TIMEZONE = ZoneInfo("Asia/Riyadh")


def school_now() -> datetime:
    return datetime.now(SCHOOL_TIMEZONE).replace(tzinfo=None)


def school_today() -> date:
    return datetime.now(SCHOOL_TIMEZONE).date()
