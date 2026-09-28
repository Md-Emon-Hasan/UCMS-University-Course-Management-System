-- =====================================================================
-- 01_tables.sql
-- Creates the 21 core tables of UCMS (+ 1 small helper table).
--
-- SQLite rules used everywhere in this file:
--   * No ENUM type      -> TEXT + CHECK (col IN ('a','b','c'))
--   * No BOOLEAN type   -> INTEGER + CHECK (col IN (0,1))
--   * No TIMESTAMP type -> TEXT holding ISO-8601 UTC 'YYYY-MM-DD HH:MM:SS'
--                          default = (datetime('now'))
--   * Money             -> INTEGER paisa (1500.50 BDT is stored as 150050).
--                          REAL is never used for money because floating
--                          point numbers cannot store 0.10 exactly.
--   * Dates             -> TEXT 'YYYY-MM-DD'. Times -> TEXT 'HH:MM' (24h).
--                          Zero-padded text sorts correctly, so '09:00' < '10:30'
--                          works in CHECK constraints and comparisons.
--
-- Tables are created in "foreign key order": a table is created after the
-- tables it points to. The ONE exception is the circular pair
-- departments <-> teachers (see 02_rebuild_circular_fk.sql).
-- =====================================================================


-- ---------------------------------------------------------------------
-- T1 users : login accounts for all 4 roles
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    -- COLLATE NOCASE: 'A@x.com' and 'a@x.com' count as the same email for UNIQUE
    email          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT    NOT NULL,
    role           TEXT    NOT NULL CHECK (role IN ('admin','teacher','student','accountant')),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    last_login_at  TEXT    NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T2 departments
-- CIRCULAR FK: a department has a head teacher, and every teacher belongs
-- to a department. We create departments FIRST, WITHOUT the FK on
-- head_teacher_id (teachers does not exist yet). 02_rebuild_circular_fk.sql
-- adds the FK later using SQLite's 12-step table rebuild.
-- ---------------------------------------------------------------------
CREATE TABLE departments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    code             TEXT    NOT NULL UNIQUE,
    head_teacher_id  INTEGER NULL,                 -- FK added in 02_rebuild_circular_fk.sql
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T3 teachers : 1:1 with users (user_id UNIQUE), N:1 with departments
-- ---------------------------------------------------------------------
CREATE TABLE teachers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
    department_id  INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    employee_code  TEXT    NOT NULL UNIQUE,
    first_name     TEXT    NOT NULL,
    last_name      TEXT    NOT NULL,
    phone          TEXT    NULL,
    designation    TEXT    NOT NULL CHECK (designation IN
                        ('lecturer','assistant_professor','associate_professor','professor')),
    hired_at       TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','on_leave','resigned')),
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T4 students : 1:1 with users, N:1 with departments
-- ---------------------------------------------------------------------
CREATE TABLE students (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
    department_id   INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    student_code    TEXT    NOT NULL UNIQUE,
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    admission_date  TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','suspended','graduated','dropped_out')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T5 student_profiles : strict 1:1 with students
-- The PRIMARY KEY is also the FOREIGN KEY, so a student can have at most
-- one profile, and the profile cannot exist without the student.
-- There is intentionally NO separate id column here.
-- ---------------------------------------------------------------------
CREATE TABLE student_profiles (
    student_id         INTEGER PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
    date_of_birth      TEXT    NOT NULL,
    gender             TEXT    NOT NULL CHECK (gender IN ('male','female','other')),
    blood_group        TEXT    NULL,
    address_line       TEXT    NULL,
    city               TEXT    NULL,
    postal_code        TEXT    NULL,
    guardian_name      TEXT    NOT NULL,
    guardian_phone     TEXT    NOT NULL,
    guardian_relation  TEXT    NOT NULL,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T6 semesters
-- Only ONE semester may be active. That rule is enforced by the partial
-- unique index uq_one_active_semester created right after the table.
-- ---------------------------------------------------------------------
CREATE TABLE semesters (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    code                TEXT    NOT NULL UNIQUE,
    start_date          TEXT    NOT NULL,
    end_date            TEXT    NOT NULL CHECK (end_date > start_date),
    registration_start  TEXT    NOT NULL,
    registration_end    TEXT    NOT NULL CHECK (registration_end > registration_start),
    is_active           INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0,1)),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- DB LESSON: a partial UNIQUE index only covers rows matching the WHERE.
-- Rows with is_active = 0 are not in the index at all, so any number of them
-- is fine, but a second row with is_active = 1 breaks UNIQUE.
CREATE UNIQUE INDEX uq_one_active_semester ON semesters(is_active) WHERE is_active = 1;


-- ---------------------------------------------------------------------
-- T7 courses : the course catalogue (not tied to any semester)
-- ---------------------------------------------------------------------
CREATE TABLE courses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id  INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    code           TEXT    NOT NULL UNIQUE,
    title          TEXT    NOT NULL,
    description    TEXT    NULL,
    credits        REAL    NOT NULL CHECK (credits > 0 AND credits <= 6),
    level          INTEGER NOT NULL CHECK (level BETWEEN 1 AND 4),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T8 course_prerequisites : SELF many-to-many (courses <-> courses)
-- "course_id requires prerequisite_course_id to be passed first".
-- ---------------------------------------------------------------------
CREATE TABLE course_prerequisites (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id               INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    prerequisite_course_id  INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_course_prereq UNIQUE (course_id, prerequisite_course_id),
    -- a course cannot be its own prerequisite
    CONSTRAINT chk_prereq_not_self CHECK (course_id <> prerequisite_course_id)
);


-- ---------------------------------------------------------------------
-- T9 rooms
-- ---------------------------------------------------------------------
CREATE TABLE rooms (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    building     TEXT    NOT NULL,
    room_number  TEXT    NOT NULL,
    capacity     INTEGER NOT NULL CHECK (capacity > 0),
    room_type    TEXT    NOT NULL CHECK (room_type IN ('lecture','lab','seminar')),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_room UNIQUE (building, room_number)
);


-- ---------------------------------------------------------------------
-- T10 course_offerings : one course, taught in one semester, by one teacher
-- enrolled_count is a stored counter kept in sync by triggers
-- (see 05_triggers.sql). The CHECK makes over-filling impossible even if a
-- bug skips the Python check.
-- ---------------------------------------------------------------------
CREATE TABLE course_offerings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id       INTEGER NOT NULL REFERENCES courses(id)   ON DELETE RESTRICT,
    semester_id     INTEGER NOT NULL REFERENCES semesters(id) ON DELETE RESTRICT,
    teacher_id      INTEGER NOT NULL REFERENCES teachers(id)  ON DELETE RESTRICT,
    section         TEXT    NOT NULL,
    capacity        INTEGER NOT NULL CHECK (capacity > 0),
    enrolled_count  INTEGER NOT NULL DEFAULT 0 CHECK (enrolled_count >= 0),
    status          TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','cancelled')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_offering_section UNIQUE (course_id, semester_id, section),
    CONSTRAINT chk_offering_not_over_capacity CHECK (enrolled_count <= capacity)
);


-- ---------------------------------------------------------------------
-- T11 class_schedules : weekly time slots of an offering
-- day_of_week: 0 = Sunday ... 6 = Saturday
-- Room and teacher clashes are blocked by triggers (05_triggers.sql).
-- ---------------------------------------------------------------------
CREATE TABLE class_schedules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    offering_id  INTEGER NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
    room_id      INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    day_of_week  INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time   TEXT    NOT NULL,
    end_time     TEXT    NOT NULL CHECK (end_time > start_time),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T12 enrollments : the core many-to-many junction (students <-> offerings)
-- It also carries its own data (status, marks, grade), which is why it is
-- called an "N:M with attributes" table.
-- ---------------------------------------------------------------------
CREATE TABLE enrollments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(id)         ON DELETE RESTRICT,
    offering_id   INTEGER NOT NULL REFERENCES course_offerings(id) ON DELETE RESTRICT,
    enrolled_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    status        TEXT    NOT NULL DEFAULT 'enrolled' CHECK (status IN ('enrolled','dropped','completed')),
    total_marks   REAL    NULL CHECK (total_marks IS NULL OR (total_marks BETWEEN 0 AND 100)),
    grade_point   REAL    NULL CHECK (grade_point IS NULL OR (grade_point BETWEEN 0 AND 4)),
    letter_grade  TEXT    NULL,
    dropped_at    TEXT    NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_enrollment UNIQUE (student_id, offering_id),
    -- "if status is dropped, then dropped_at must be filled"
    -- written as: NOT dropped  OR  has a date
    CONSTRAINT chk_dropped_has_date CHECK (status <> 'dropped' OR dropped_at IS NOT NULL)
);


-- ---------------------------------------------------------------------
-- T13 attendance : one row per enrollment per class date
-- ---------------------------------------------------------------------
CREATE TABLE attendance (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id  INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    class_date     TEXT    NOT NULL,
    status         TEXT    NOT NULL CHECK (status IN ('present','absent','late','excused')),
    remarks        TEXT    NULL,
    recorded_by    INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_attendance_day UNIQUE (enrollment_id, class_date)
);


-- ---------------------------------------------------------------------
-- T14 assessments : quizzes, exams ... of an offering
-- ---------------------------------------------------------------------
CREATE TABLE assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    offering_id     INTEGER NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
    title           TEXT    NOT NULL,
    type            TEXT    NOT NULL CHECK (type IN ('quiz','assignment','midterm','final','project')),
    max_marks       REAL    NOT NULL CHECK (max_marks > 0),
    weight_percent  REAL    NOT NULL CHECK (weight_percent > 0 AND weight_percent <= 100),
    due_date        TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T15 assessment_results : marks of one enrollment in one assessment
-- "marks must not exceed max_marks" needs data from ANOTHER table, and a
-- CHECK can only see its own row, so that rule lives in a trigger
-- (trg_validate_marks).
-- ---------------------------------------------------------------------
CREATE TABLE assessment_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id   INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    enrollment_id   INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    marks_obtained  REAL    NOT NULL CHECK (marks_obtained >= 0),
    submitted_at    TEXT    NULL,
    graded_by       INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_result UNIQUE (assessment_id, enrollment_id)
);


-- ---------------------------------------------------------------------
-- T16 fee_structures : price list per semester
-- department_id NULL  = applies to every department (global row)
-- department_id set   = department-specific row (overrides the global one)
-- amount is INTEGER paisa.
-- ---------------------------------------------------------------------
CREATE TABLE fee_structures (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    semester_id    INTEGER NOT NULL REFERENCES semesters(id)  ON DELETE RESTRICT,
    department_id  INTEGER NULL     REFERENCES departments(id) ON DELETE RESTRICT,
    fee_type       TEXT    NOT NULL CHECK (fee_type IN ('tuition','admission','lab','library','exam','late_fine')),
    amount         INTEGER NOT NULL CHECK (amount >= 0),   -- paisa
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    -- DB LESSON: in SQLite (and standard SQL) NULLs are all "different", so
    -- this UNIQUE does NOT stop two global rows (department_id NULL) with
    -- the same semester + fee_type. A partial unique index in
    -- 03_indexes.sql closes that gap.
    CONSTRAINT uq_fee_structure UNIQUE (semester_id, department_id, fee_type)
);


-- ---------------------------------------------------------------------
-- T17 invoices : one invoice per student per semester
-- ---------------------------------------------------------------------
CREATE TABLE invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(id)  ON DELETE RESTRICT,
    semester_id   INTEGER NOT NULL REFERENCES semesters(id) ON DELETE RESTRICT,
    invoice_no    TEXT    NOT NULL UNIQUE,
    total_amount  INTEGER NOT NULL CHECK (total_amount >= 0),       -- paisa
    paid_amount   INTEGER NOT NULL DEFAULT 0 CHECK (paid_amount >= 0), -- paisa
    issued_at     TEXT    NOT NULL,
    due_date      TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'unpaid' CHECK (status IN ('unpaid','partial','paid','overdue')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_invoice_student_semester UNIQUE (student_id, semester_id),
    CONSTRAINT chk_invoice_not_overpaid CHECK (paid_amount <= total_amount)
);


-- ---------------------------------------------------------------------
-- T18 invoice_items : the lines of an invoice
-- fee_structure_id is SET NULL on delete: the line (and its amount) stays
-- on the invoice even if the price list row is removed later.
-- ---------------------------------------------------------------------
CREATE TABLE invoice_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id        INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    fee_structure_id  INTEGER NULL     REFERENCES fee_structures(id) ON DELETE SET NULL,
    description       TEXT    NOT NULL,
    amount            INTEGER NOT NULL CHECK (amount >= 0),   -- paisa
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T19 payments
-- transaction_ref is NULL for cash. UNIQUE allows many NULLs, but a real
-- reference number can only be used once.
-- ---------------------------------------------------------------------
CREATE TABLE payments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id       INTEGER NOT NULL REFERENCES invoices(id) ON DELETE RESTRICT,
    amount           INTEGER NOT NULL CHECK (amount > 0),   -- paisa
    method           TEXT    NOT NULL CHECK (method IN ('cash','bank','bkash','nagad','card')),
    transaction_ref  TEXT    NULL UNIQUE,
    paid_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    received_by      INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T20 announcements
-- target_role NULL          = everyone
-- target_department_id NULL = every department
-- ---------------------------------------------------------------------
CREATE TABLE announcements (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    title                 TEXT    NOT NULL,
    body                  TEXT    NOT NULL,
    posted_by             INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    target_role           TEXT    NULL CHECK (target_role IS NULL OR
                              target_role IN ('admin','teacher','student','accountant')),
    target_department_id  INTEGER NULL REFERENCES departments(id) ON DELETE CASCADE,
    published_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at            TEXT    NULL,
    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------
-- T21 audit_logs : written ONLY by triggers (see 05_triggers.sql)
-- No created_at/updated_at: a log row is never updated, so changed_at is enough.
-- old_data / new_data hold JSON text made with json_object(...).
-- ---------------------------------------------------------------------
CREATE TABLE audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT    NOT NULL,
    record_id   INTEGER NOT NULL,
    action      TEXT    NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE')),
    old_data    TEXT    NULL,   -- JSON string
    new_data    TEXT    NULL,   -- JSON string
    changed_by  INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    changed_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- =====================================================================
-- Helper table (NOT one of the 21 core tables)
-- _audit_actor holds "who is making the current change". Python writes it
-- at the start of every write transaction (app/database.py -> set_actor),
-- and the audit triggers read it.
-- The CHECK (id = 1) makes it a guaranteed single-row table.
-- =====================================================================
CREATE TABLE _audit_actor (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    user_id  INTEGER NULL
);
INSERT INTO _audit_actor (id, user_id) VALUES (1, NULL);
