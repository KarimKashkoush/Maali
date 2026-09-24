CREATE TABLE schools (
 id SERIAL PRIMARY KEY, name VARCHAR(150) NOT NULL UNIQUE, timezone VARCHAR(80) NOT NULL DEFAULT 'Asia/Riyadh', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE stages (
 id SERIAL PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), name VARCHAR(100) NOT NULL,
 UNIQUE(school_id,name), UNIQUE(id,school_id)
);
CREATE TABLE classrooms (
 id SERIAL PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), stage_id INTEGER NOT NULL,
 classroom_name VARCHAR(150) NOT NULL, attendance_start TIME NOT NULL DEFAULT '07:00',
 grace_minutes INTEGER NOT NULL DEFAULT 10 CHECK(grace_minutes BETWEEN 0 AND 180),
 absence_after_minutes INTEGER NOT NULL DEFAULT 30 CHECK(absence_after_minutes BETWEEN 0 AND 360),
 attendance_end TIME NOT NULL DEFAULT '14:00', weekdays INTEGER[] NOT NULL DEFAULT '{0,1,2,3,4}',
 FOREIGN KEY(stage_id,school_id) REFERENCES stages(id,school_id), UNIQUE(school_id,stage_id,classroom_name),
 CHECK(attendance_end > attendance_start), CHECK(absence_after_minutes >= grace_minutes),
 CHECK(cardinality(weekdays) BETWEEN 1 AND 7 AND weekdays <@ ARRAY[0,1,2,3,4,5,6])
);
CREATE TABLE students (
 id SERIAL PRIMARY KEY, full_name VARCHAR(150) NOT NULL, class_id INTEGER NOT NULL REFERENCES classrooms(id),
 is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX students_class ON students(class_id) WHERE is_active;
CREATE TABLE student_images (
 id SERIAL PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id), type VARCHAR(20) NOT NULL,
 storage_key VARCHAR(300) NOT NULL UNIQUE, embedding JSONB, model VARCHAR(50), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(student_id,type), CHECK(type IN ('primary','front','left','right','up','down'))
);
CREATE TABLE attendance_days (
 id SERIAL PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classrooms(id), attendance_date DATE NOT NULL,
 timezone VARCHAR(80) NOT NULL, schedule JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(class_id,attendance_date)
);
CREATE TABLE attendance_records (
 id SERIAL PRIMARY KEY, day_id INTEGER NOT NULL REFERENCES attendance_days(id), student_id INTEGER NOT NULL REFERENCES students(id),
 student_name VARCHAR(150) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending',
 check_in_at TIMESTAMPTZ, late_minutes INTEGER NOT NULL DEFAULT 0, recognition_confidence REAL,
 source VARCHAR(20), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(day_id,student_id),
 CHECK(status IN ('pending','present','late','absent','not_scheduled'))
);
CREATE TABLE audit_log (
 id BIGSERIAL PRIMARY KEY, actor VARCHAR(150) NOT NULL, action VARCHAR(100) NOT NULL,
 entity_id INTEGER, details JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE auth_sessions (
 token_hash CHAR(64) PRIMARY KEY, username VARCHAR(150) NOT NULL, expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX attendance_day_student ON attendance_records(student_id,day_id);
