CREATE TABLE student_enrollments (
 id SERIAL PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id), class_id INTEGER NOT NULL REFERENCES classrooms(id),
 enrolled_on DATE NOT NULL, withdrawn_on DATE, CHECK(withdrawn_on IS NULL OR withdrawn_on >= enrolled_on)
);
CREATE UNIQUE INDEX one_current_enrollment ON student_enrollments(student_id) WHERE withdrawn_on IS NULL;
CREATE INDEX enrollment_class_dates ON student_enrollments(class_id,enrolled_on,withdrawn_on);
