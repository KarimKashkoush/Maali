CREATE TABLE classroom_schedule_versions (
 id SERIAL PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classrooms(id), effective_on DATE NOT NULL,
 timezone VARCHAR(80) NOT NULL, schedule JSONB NOT NULL, UNIQUE(class_id,effective_on)
);
INSERT INTO classroom_schedule_versions(class_id,effective_on,timezone,schedule)
 SELECT c.id,COALESCE((SELECT min(d.attendance_date) FROM attendance_days d WHERE d.class_id=c.id),CURRENT_DATE),s.timezone,
 jsonb_build_object('attendance_start',c.attendance_start,'attendance_end',c.attendance_end,'grace_minutes',c.grace_minutes,'absence_after_minutes',c.absence_after_minutes,'weekdays',c.weekdays)
 FROM classrooms c JOIN schools s ON s.id=c.school_id;
ALTER TABLE classroom_schedule_versions ENABLE ROW LEVEL SECURITY;
