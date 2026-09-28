-- =====================================================================
-- 01_basic.sql  (Q1 - Q8)
-- Basics: SELECT, JOIN, WHERE, ORDER BY, LIMIT and "current semester" filters.
--
-- Run:  python scripts/run_queries.py queries/01_basic.sql
-- Every query is standalone, so you can also copy one into any SQLite tool.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1. List all ACTIVE students with their department, sorted by
--     department and then by name.
-- DEMONSTRATES: INNER JOIN, WHERE on a text column, ORDER BY on several
--     columns, and || (string concatenation).
-- ---------------------------------------------------------------------
SELECT
    d.code                                AS dept,
    s.student_code,
    s.first_name || ' ' || s.last_name    AS student_name,
    s.admission_date
FROM students s
JOIN departments d ON d.id = s.department_id     -- JOIN = only rows that match on both sides
WHERE s.status = 'active'
ORDER BY d.code, s.last_name, s.first_name;


-- ---------------------------------------------------------------------
-- Q2. Offerings of the CURRENT (active) semester with course, teacher and
--     seats left.
-- DEMONSTRATES: joining 4 tables, filtering by the active semester, and a
--     computed column (capacity - enrolled_count).
-- ---------------------------------------------------------------------
SELECT
    c.code                                 AS course,
    c.title,
    co.section,
    t.first_name || ' ' || t.last_name     AS teacher,
    co.capacity,
    co.enrolled_count,
    co.capacity - co.enrolled_count        AS seats_left,
    co.status
FROM course_offerings co
JOIN semesters sem ON sem.id = co.semester_id
JOIN courses   c   ON c.id   = co.course_id
JOIN teachers  t   ON t.id   = co.teacher_id
WHERE sem.is_active = 1                 -- "current semester" = the one active row
ORDER BY c.code, co.section;


-- ---------------------------------------------------------------------
-- Q3. Weekly routine of the demo teacher (teacher@ucms.edu) in the
--     active semester.
-- DEMONSTRATES: CASE to turn a number into a label, and finding a row by
--     email instead of a hard-coded id.
-- ---------------------------------------------------------------------
SELECT
    CASE cs.day_of_week
        WHEN 0 THEN 'Sunday'    WHEN 1 THEN 'Monday'  WHEN 2 THEN 'Tuesday'
        WHEN 3 THEN 'Wednesday' WHEN 4 THEN 'Thursday' WHEN 5 THEN 'Friday'
        ELSE 'Saturday'
    END                                    AS day,
    cs.start_time,
    cs.end_time,
    c.code || '-' || co.section            AS class,
    r.building || ' ' || r.room_number     AS room
FROM class_schedules cs
JOIN course_offerings co ON co.id  = cs.offering_id
JOIN courses          c  ON c.id   = co.course_id
JOIN rooms            r  ON r.id   = cs.room_id
JOIN semesters        sem ON sem.id = co.semester_id
JOIN teachers         t  ON t.id   = co.teacher_id
JOIN users            u  ON u.id   = t.user_id
WHERE u.email = 'teacher@ucms.edu'
  AND sem.is_active = 1
ORDER BY cs.day_of_week, cs.start_time;


-- ---------------------------------------------------------------------
-- Q4. Upper-level CSE courses (level 3 or 4) worth at least 3 credits.
-- DEMONSTRATES: IN (...), BETWEEN, and AND in one WHERE.
-- ---------------------------------------------------------------------
SELECT c.code, c.title, c.level, c.credits
FROM courses c
JOIN departments d ON d.id = c.department_id
WHERE d.code IN ('CSE')
  AND c.level BETWEEN 3 AND 4        -- BETWEEN includes both ends
  AND c.credits >= 3
ORDER BY c.level, c.code;


-- ---------------------------------------------------------------------
-- Q5. What is the demo student (student@ucms.edu) taking right now?
-- DEMONSTRATES: filtering on the junction table (enrollments) and on the
--     active semester at the same time.
-- ---------------------------------------------------------------------
SELECT
    c.code, c.title, c.credits, co.section,
    t.first_name || ' ' || t.last_name AS teacher,
    e.enrolled_at
FROM enrollments e
JOIN students         s   ON s.id   = e.student_id
JOIN users            u   ON u.id   = s.user_id
JOIN course_offerings co  ON co.id  = e.offering_id
JOIN courses          c   ON c.id   = co.course_id
JOIN teachers         t   ON t.id   = co.teacher_id
JOIN semesters        sem ON sem.id = co.semester_id
WHERE u.email = 'student@ucms.edu'
  AND sem.is_active = 1
  AND e.status = 'enrolled';


-- ---------------------------------------------------------------------
-- Q6. Search students whose first OR last name contains "rahman".
-- DEMONSTRATES: LIKE with % wildcards. In SQLite, LIKE ignores upper/lower
--     case for English letters, so 'rahman' also finds 'Rahman'.
-- ---------------------------------------------------------------------
SELECT student_code, first_name, last_name, status
FROM students
WHERE first_name LIKE '%rahman%'
   OR last_name  LIKE '%rahman%'
ORDER BY last_name, first_name
LIMIT 15;


-- ---------------------------------------------------------------------
-- Q7. Announcements a student can see today: meant for everyone or for
--     students, already published, and not expired.
-- DEMONSTRATES: NULL handling. "expires_at > now" is NOT true when
--     expires_at is NULL (the result is NULL = unknown), so we must add
--     "expires_at IS NULL" explicitly.
-- ---------------------------------------------------------------------
SELECT title, target_role, published_at, expires_at
FROM announcements
WHERE (target_role IS NULL OR target_role = 'student')
  AND published_at <= datetime('now')
  AND (expires_at IS NULL OR expires_at > datetime('now'))
ORDER BY published_at DESC;


-- ---------------------------------------------------------------------
-- Q8. The 20 most recent payments of the last 30 days, amounts in taka.
-- DEMONSTRATES: date arithmetic with datetime('now', '-30 days'), LIMIT,
--     and turning INTEGER paisa into taka for display only
--     (amount / 100.0 -> decimal; printf formats 2 decimal places).
-- ---------------------------------------------------------------------
SELECT
    p.paid_at,
    i.invoice_no,
    p.method,
    printf('%.2f', p.amount / 100.0)   AS amount_taka,
    p.transaction_ref
FROM payments p
JOIN invoices i ON i.id = p.invoice_id
WHERE p.paid_at >= datetime('now', '-30 days')
ORDER BY p.paid_at DESC
LIMIT 20;
