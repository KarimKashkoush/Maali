class LiveAttendanceService:

    def start(
        self,
        session_id: int,
    ):
        recognition.reload_known_faces(db)