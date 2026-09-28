-- =====================================================================
-- 03_outer_joins.sql  (Q19 - Q23)
-- "Find the missing things" with LEFT JOIN ... WHERE right_side.id IS NULL.
--
-- How it works:
--   A LEFT JOIN keeps EVERY row of the left table. If there is no match on
--   the right, the right-hand columns are filled with NULL. So "right.id IS
--   NULL" keeps exactly the left rows that have NO match: the "anti-join".
--
-- (NOT EXISTS (...) gives the same result. Q20 shows both ways.)
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q19. Students who have NEVER enrolled in anything.
-- DEMONSTRATES: the classic LEFT JOIN anti-join.
-- Expected: the 5 brand-new admissions (one per department).
-- ---------------------------------------------------------------------
SELECT s.student_code, s.first_name || ' ' || s.last_name AS name, s.admission_date, s.status
FROM students s
LEFT JOIN enrollments e ON e.student_id = s.id
WHERE e.id IS NULL
ORDER BY s.student_code;


-- ---------------------------------------------------------------------
-- Q20. Courses that were NEVER offered in any semester.
-- DEMONSTRATES: the same question written two ways: LEFT JOIN and
--     NOT EXISTS. Both give identical rows; try EXPLAIN QUERY PLAN on each.
-- ---------------------------------------------------------------------
-- Way 1: LEFT JOIN
SELECT c.code, c.title, c.level
FROM courses c
LEFT JOIN course_offerings co ON co.course_id = c.id
WHERE co.id IS NULL
ORDER BY c.code;

-- Way 2: NOT EXISTS (reads like English: "courses where no offering exists")
SELECT c.code, c.title, c.level
FROM courses c
WHERE NOT EXISTS (SELECT 1 FROM course_offerings co WHERE co.course_id = c.id)
ORDER BY c.code;


-- ---------------------------------------------------------------------
-- Q21. Teachers who teach NOTHING in the active semester.
-- DEMONSTRATES: the most common outer-join mistake.
--   The semester condition MUST go in the ON clause. If you put
--   "sem.is_active = 1" in the WHERE instead, rows with NULLs (no match)
--   fail that test and disappear, which quietly turns the LEFT JOIN
--   back into an INNER JOIN and returns nothing useful.
-- ---------------------------------------------------------------------
SELECT
    t.employee_code,
    t.first_name || ' ' || t.last_name AS teacher,
    d.code                             AS dept,
    t.status
FROM teachers t
JOIN departments d ON d.id = t.department_id
LEFT JOIN course_offerings co
       ON co.teacher_id = t.id
      AND co.status <> 'cancelled'
      AND co.semester_id = (SELECT id FROM semesters WHERE is_active = 1)   -- <- in ON, not WHERE
WHERE co.id IS NULL
ORDER BY d.code, teacher;


-- ---------------------------------------------------------------------
-- Q22. Invoices with ZERO payments, and how much is owed on them.
-- DEMONSTRATES: anti-join on a money table, with paisa -> taka for display.
-- ---------------------------------------------------------------------
SELECT
    i.invoice_no,
    s.student_code,
    printf('%.2f', i.total_amount / 100.0) AS owed_taka,
    i.due_date,
    i.status
FROM invoices i
JOIN students s ON s.id = i.student_id
LEFT JOIN payments p ON p.invoice_id = i.id
WHERE p.id IS NULL
ORDER BY i.due_date, i.invoice_no;


-- ---------------------------------------------------------------------
-- Q23. Offerings that have NO class schedule (no room and time yet).
-- DEMONSTRATES: an anti-join combined with extra display joins.
-- Expected: 2 rows in the active semester (one cancelled, one "TBA").
-- ---------------------------------------------------------------------
SELECT
    sem.code                    AS semester,
    c.code || '-' || co.section AS offering,
    co.status,
    co.enrolled_count
FROM course_offerings co
JOIN courses   c   ON c.id   = co.course_id
JOIN semesters sem ON sem.id = co.semester_id
LEFT JOIN class_schedules cs ON cs.offering_id = co.id
WHERE cs.id IS NULL
ORDER BY sem.start_date, offering;
