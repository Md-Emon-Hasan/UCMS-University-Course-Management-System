-- =====================================================================
-- 04_views.sql
-- A VIEW is a saved SELECT with a name. It stores no data: every time you
-- query it, SQLite runs the SELECT again, so a view is always up to date.
-- Views hide long JOINs, so the API can simply run
--     SELECT * FROM v_student_transcript WHERE student_id = ?
--
-- The columns listed in the spec come first. A few extra id columns come
-- after them, so the API can filter the views easily.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1) v_student_transcript
-- One row per COMPLETED course of a student (dropped or ongoing courses are
-- not on a transcript).
-- ---------------------------------------------------------------------
CREATE VIEW v_student_transcript AS
SELECT
    st.id                                   AS student_id,
    st.student_code                         AS student_code,
    st.first_name || ' ' || st.last_name    AS full_name,
    sem.code                                AS semester_code,
    c.code                                  AS course_code,
    c.title                                 AS course_title,
    c.credits                               AS credits,
    e.letter_grade                          AS letter_grade,
    e.grade_point                           AS grade_point,
    -- extra columns
    e.id                                    AS enrollment_id,
    sem.id                                  AS semester_id,
    sem.start_date                          AS semester_start,
    e.total_marks                           AS total_marks
FROM enrollments e
JOIN students         st  ON st.id  = e.student_id
JOIN course_offerings co  ON co.id  = e.offering_id
JOIN courses          c   ON c.id   = co.course_id
JOIN semesters        sem ON sem.id = co.semester_id
WHERE e.status = 'completed';


-- ---------------------------------------------------------------------
-- 2) v_offering_summary
-- fill_percent = enrolled_count / capacity * 100
-- We write 100.0 (not 100) on purpose: in SQL, integer / integer gives an
-- integer, so 25 / 40 = 0. Using 100.0 makes the maths use decimals.
--
-- enrolled_count counts only students with status 'enrolled' (spec rule).
-- total_students also counts 'completed' students, which is useful for
-- past semesters, where everyone is 'completed'.
-- ---------------------------------------------------------------------
CREATE VIEW v_offering_summary AS
SELECT
    co.id                                   AS offering_id,
    c.code                                  AS course_code,
    c.title                                 AS title,
    co.section                              AS section,
    t.first_name || ' ' || t.last_name      AS teacher_name,
    sem.code                                AS semester_code,
    co.capacity                             AS capacity,
    co.enrolled_count                       AS enrolled_count,
    ROUND(100.0 * co.enrolled_count / co.capacity, 1) AS fill_percent,
    -- extra columns
    co.course_id                            AS course_id,
    co.semester_id                          AS semester_id,
    co.teacher_id                           AS teacher_id,
    c.department_id                         AS department_id,
    c.credits                               AS credits,
    co.status                               AS status,
    (SELECT COUNT(*) FROM enrollments e
      WHERE e.offering_id = co.id AND e.status <> 'dropped') AS total_students
FROM course_offerings co
JOIN courses   c   ON c.id   = co.course_id
JOIN teachers  t   ON t.id   = co.teacher_id
JOIN semesters sem ON sem.id = co.semester_id;


-- ---------------------------------------------------------------------
-- 3) v_attendance_percentage
-- One row per (not dropped) enrollment.
-- Counting rule: 'present' and 'late' count as attended; 'absent' and
-- 'excused' do not. (DECISIONS.md)
-- LEFT JOIN keeps enrollments that have no attendance rows yet; for them
-- total_classes = 0 and attendance_percent is NULL (nothing to measure).
-- ---------------------------------------------------------------------
CREATE VIEW v_attendance_percentage AS
SELECT
    e.id                                    AS enrollment_id,
    e.student_id                            AS student_id,
    e.offering_id                           AS offering_id,
    COUNT(a.id)                             AS total_classes,
    -- SUM of a true/false test counts the matching rows (true = 1, false = 0)
    COALESCE(SUM(a.status IN ('present','late')), 0) AS present_count,
    CASE
        WHEN COUNT(a.id) = 0 THEN NULL
        ELSE ROUND(100.0 * SUM(a.status IN ('present','late')) / COUNT(a.id), 1)
    END                                     AS attendance_percent
FROM enrollments e
LEFT JOIN attendance a ON a.enrollment_id = e.id
WHERE e.status <> 'dropped'
GROUP BY e.id, e.student_id, e.offering_id;


-- ---------------------------------------------------------------------
-- 4) v_outstanding_dues
-- Only invoices that still have money to pay.
-- Amounts are INTEGER paisa (the API turns them into taka).
-- days_overdue: julianday() turns a date into a day number, so the
-- difference is a number of days. MAX(0, ...) gives 0 when not yet due.
-- status: the stored status, except that an unpaid/partial invoice past its
-- due date is shown as 'overdue'.
-- ---------------------------------------------------------------------
CREATE VIEW v_outstanding_dues AS
SELECT
    st.id                                   AS student_id,
    st.student_code                         AS student_code,
    st.first_name || ' ' || st.last_name    AS name,
    i.invoice_no                            AS invoice_no,
    i.total_amount                          AS total_amount,
    i.paid_amount                           AS paid_amount,
    i.total_amount - i.paid_amount          AS due_amount,
    CASE
        WHEN date(i.due_date) < date('now') THEN 'overdue'
        ELSE i.status
    END                                     AS status,
    MAX(0, CAST(julianday(date('now')) - julianday(i.due_date) AS INTEGER)) AS days_overdue,
    -- extra columns
    i.id                                    AS invoice_id,
    i.semester_id                           AS semester_id,
    i.due_date                              AS due_date,
    st.department_id                        AS department_id
FROM invoices i
JOIN students st ON st.id = i.student_id
WHERE i.paid_amount < i.total_amount;


-- ---------------------------------------------------------------------
-- 5) v_teacher_workload
-- One row per teacher per semester (cancelled offerings are ignored).
-- total_students is computed in a sub-query per offering. If we JOINed
-- enrollments directly, every offering row would be repeated once per
-- student, and SUM(credits) would be far too big. This is the classic
-- "join fan-out" mistake.
-- ---------------------------------------------------------------------
CREATE VIEW v_teacher_workload AS
SELECT
    t.id                                    AS teacher_id,
    t.first_name || ' ' || t.last_name      AS teacher_name,
    sem.code                                AS semester_code,
    COUNT(co.id)                            AS course_count,
    SUM(c.credits)                          AS total_credits,
    SUM((SELECT COUNT(*) FROM enrollments e
          WHERE e.offering_id = co.id AND e.status <> 'dropped')) AS total_students,
    -- extra columns
    sem.id                                  AS semester_id,
    t.department_id                         AS department_id
FROM teachers t
JOIN course_offerings co  ON co.teacher_id = t.id AND co.status <> 'cancelled'
JOIN courses          c   ON c.id   = co.course_id
JOIN semesters        sem ON sem.id = co.semester_id
GROUP BY t.id, sem.id;
