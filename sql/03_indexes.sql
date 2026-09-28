-- =====================================================================
-- 03_indexes.sql
-- Indexes make lookups fast. Without an index SQLite must read EVERY row
-- (a "full table scan"). With one, it jumps straight to the right rows,
-- like the index at the back of a book.
--
-- Naming: idx_<table>_<columns>   (uq_... = unique index)
--
-- DB LESSON: SQLite does NOT index foreign-key columns automatically
-- (only PRIMARY KEY and UNIQUE get an automatic index). An un-indexed FK
-- makes JOINs slow, and it also makes ON DELETE checks on the parent table
-- scan the whole child table.
--
-- Try it: EXPLAIN QUERY PLAN SELECT * FROM enrollments WHERE offering_id = 5;
--   -> "SEARCH enrollments USING INDEX idx_enrollments_offering_id"
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1) Foreign-key indexes (17)
-- ---------------------------------------------------------------------
CREATE INDEX idx_teachers_department_id            ON teachers(department_id);
CREATE INDEX idx_students_department_id            ON students(department_id);
CREATE INDEX idx_courses_department_id             ON courses(department_id);

CREATE INDEX idx_course_offerings_course_id        ON course_offerings(course_id);
CREATE INDEX idx_course_offerings_semester_id      ON course_offerings(semester_id);
CREATE INDEX idx_course_offerings_teacher_id       ON course_offerings(teacher_id);

-- Note: UNIQUE(student_id, offering_id) already creates an index whose
-- LEFTMOST column is student_id, so SQLite could use it for student_id
-- lookups too. We still create the single-column index because the spec
-- asks for it. Compare both with EXPLAIN QUERY PLAN as an exercise.
CREATE INDEX idx_enrollments_student_id            ON enrollments(student_id);
CREATE INDEX idx_enrollments_offering_id           ON enrollments(offering_id);

CREATE INDEX idx_attendance_enrollment_id          ON attendance(enrollment_id);

CREATE INDEX idx_assessment_results_enrollment_id  ON assessment_results(enrollment_id);
CREATE INDEX idx_assessment_results_assessment_id  ON assessment_results(assessment_id);

CREATE INDEX idx_invoices_student_id               ON invoices(student_id);
CREATE INDEX idx_payments_invoice_id               ON payments(invoice_id);

CREATE INDEX idx_class_schedules_offering_id       ON class_schedules(offering_id);
CREATE INDEX idx_class_schedules_room_id           ON class_schedules(room_id);

CREATE INDEX idx_invoice_items_invoice_id          ON invoice_items(invoice_id);
CREATE INDEX idx_announcements_target_department_id ON announcements(target_department_id);


-- ---------------------------------------------------------------------
-- 2) Composite indexes (4)
-- Column ORDER matters: the index can be used for (a) and for (a, b),
-- but NOT for (b) alone. Put the column you filter by "=" first.
-- ---------------------------------------------------------------------

-- "open offerings of this semester"
CREATE INDEX idx_course_offerings_semester_status  ON course_offerings(semester_id, status);

-- "who was absent on 2025-03-10"
CREATE INDEX idx_attendance_date_status            ON attendance(class_date, status);

-- "students still enrolled in offering 12"
CREATE INDEX idx_enrollments_offering_status       ON enrollments(offering_id, status);

-- "full history of enrollment 42" in the audit log
CREATE INDEX idx_audit_logs_table_record           ON audit_logs(table_name, record_id);


-- ---------------------------------------------------------------------
-- 3) Partial indexes (3)
-- A partial index only stores rows that match its WHERE clause, so it is
-- smaller and faster. SQLite uses it only when the query's WHERE clause
-- contains the same condition.
-- ---------------------------------------------------------------------
CREATE INDEX idx_students_active       ON students(id)          WHERE status = 'active';
CREATE INDEX idx_invoices_unpaid       ON invoices(student_id)  WHERE status <> 'paid';
CREATE INDEX idx_course_offerings_open ON course_offerings(id)  WHERE status = 'open';


-- ---------------------------------------------------------------------
-- 4) Extra: close the "NULL is never equal to NULL" gap in fee_structures
-- UNIQUE(semester_id, department_id, fee_type) allows two GLOBAL rows
-- (department_id IS NULL) for the same semester + fee type, because
-- NULL <> NULL. This partial unique index forbids that. (DECISIONS.md D8)
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX uq_fee_structures_global
    ON fee_structures(semester_id, fee_type)
    WHERE department_id IS NULL;
