-- =====================================================================
-- 02_aggregates.sql  (Q9 - Q18)
-- Aggregates: COUNT, SUM, AVG, MIN, MAX with GROUP BY and HAVING.
--
-- Remember the order SQL runs a query in:
--   FROM/JOIN -> WHERE (filters rows) -> GROUP BY -> HAVING (filters groups)
--   -> SELECT -> ORDER BY -> LIMIT
-- So WHERE cannot use COUNT(*), but HAVING can.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q9. How many students does each department have?
-- DEMONSTRATES: GROUP BY + COUNT(*). One output row per group.
-- ---------------------------------------------------------------------
SELECT d.code, d.name, COUNT(*) AS students
FROM students s
JOIN departments d ON d.id = s.department_id
GROUP BY d.id, d.code, d.name
ORDER BY students DESC, d.code;


-- ---------------------------------------------------------------------
-- Q10. Students per department AND status.
-- DEMONSTRATES: GROUP BY on two columns (one row per combination), plus
--     "conditional aggregation": SUM(condition) counts rows where the
--     condition is true, because true = 1 and false = 0 in SQLite.
-- ---------------------------------------------------------------------
SELECT
    d.code                             AS dept,
    SUM(s.status = 'active')           AS active,
    SUM(s.status = 'suspended')        AS suspended,
    SUM(s.status = 'graduated')        AS graduated,
    SUM(s.status = 'dropped_out')      AS dropped_out,
    COUNT(*)                           AS total
FROM students s
JOIN departments d ON d.id = s.department_id
GROUP BY d.code
ORDER BY d.code;


-- ---------------------------------------------------------------------
-- Q11. Average grade point per course, only for courses with at least
--      30 graded students.
-- DEMONSTRATES: AVG, ROUND, and HAVING (a filter on groups, which runs
--     AFTER grouping; WHERE could not use COUNT(*) here).
-- ---------------------------------------------------------------------
SELECT
    c.code,
    c.title,
    COUNT(*)                       AS graded_students,
    ROUND(AVG(e.grade_point), 2)   AS avg_grade_point,
    MIN(e.total_marks)             AS lowest_marks,
    MAX(e.total_marks)             AS highest_marks
FROM enrollments e
JOIN course_offerings co ON co.id = e.offering_id
JOIN courses          c  ON c.id  = co.course_id
WHERE e.status = 'completed'
GROUP BY c.id, c.code, c.title
HAVING COUNT(*) >= 30
ORDER BY avg_grade_point DESC;


-- ---------------------------------------------------------------------
-- Q12. Teaching history per teacher: number of offerings, number of
--      DIFFERENT courses, and number of semesters taught.
-- DEMONSTRATES: COUNT(*) vs COUNT(DISTINCT col). Teaching CSE101 in 3
--     semesters is 3 offerings but only 1 distinct course.
-- ---------------------------------------------------------------------
SELECT
    t.employee_code,
    t.first_name || ' ' || t.last_name   AS teacher,
    COUNT(*)                             AS offerings,
    COUNT(DISTINCT co.course_id)         AS distinct_courses,
    COUNT(DISTINCT co.semester_id)       AS semesters_taught
FROM teachers t
JOIN course_offerings co ON co.teacher_id = t.id
WHERE co.status <> 'cancelled'
GROUP BY t.id
ORDER BY offerings DESC, teacher;


-- ---------------------------------------------------------------------
-- Q13. Money collected per payment method, with each method's share of
--      the total.
-- DEMONSTRATES: SUM on INTEGER paisa (exact, no rounding errors), and a
--     scalar sub-query (SELECT SUM(...) FROM payments) used as a divisor.
-- ---------------------------------------------------------------------
SELECT
    method,
    COUNT(*)                                        AS payments,
    printf('%.2f', SUM(amount) / 100.0)             AS collected_taka,
    ROUND(100.0 * SUM(amount) / (SELECT SUM(amount) FROM payments), 1) AS share_percent
FROM payments
GROUP BY method
ORDER BY SUM(amount) DESC;


-- ---------------------------------------------------------------------
-- Q14. Billed vs collected vs outstanding, per semester.
-- DEMONSTRATES: several SUMs in one query, and arithmetic between aggregates.
-- ---------------------------------------------------------------------
SELECT
    sem.code                                                     AS semester,
    COUNT(*)                                                     AS invoices,
    printf('%.2f', SUM(i.total_amount) / 100.0)                  AS billed_taka,
    printf('%.2f', SUM(i.paid_amount) / 100.0)                   AS collected_taka,
    printf('%.2f', (SUM(i.total_amount) - SUM(i.paid_amount)) / 100.0) AS outstanding_taka,
    ROUND(100.0 * SUM(i.paid_amount) / SUM(i.total_amount), 1)   AS collection_rate
FROM invoices i
JOIN semesters sem ON sem.id = i.semester_id
GROUP BY sem.id
ORDER BY sem.start_date;


-- ---------------------------------------------------------------------
-- Q15. Average attendance per department in the active semester.
-- DEMONSTRATES: aggregating over a VIEW (v_attendance_percentage) as if
--     it were a table.
-- ---------------------------------------------------------------------
SELECT
    d.code                                AS dept,
    COUNT(*)                              AS enrollments,
    ROUND(AVG(v.attendance_percent), 1)   AS avg_attendance_percent,
    SUM(v.attendance_percent < 75)        AS below_75
FROM v_attendance_percentage v
JOIN students         s   ON s.id   = v.student_id
JOIN departments      d   ON d.id   = s.department_id
JOIN course_offerings co  ON co.id  = v.offering_id
JOIN semesters        sem ON sem.id = co.semester_id
WHERE sem.is_active = 1
  AND v.total_classes > 0
GROUP BY d.code
ORDER BY avg_attendance_percent;


-- ---------------------------------------------------------------------
-- Q16. Letter-grade distribution per semester as a "pivot table"
--      (one column per grade).
-- DEMONSTRATES: pivoting rows into columns with SUM(CASE ...), a classic
--     reporting trick (SQLite has no PIVOT keyword).
-- ---------------------------------------------------------------------
SELECT
    sem.code AS semester,
    SUM(CASE WHEN e.letter_grade = 'A+'                 THEN 1 ELSE 0 END) AS "A+",
    SUM(CASE WHEN e.letter_grade IN ('A', 'A-')         THEN 1 ELSE 0 END) AS "A/A-",
    SUM(CASE WHEN e.letter_grade IN ('B+', 'B', 'B-')   THEN 1 ELSE 0 END) AS "B range",
    SUM(CASE WHEN e.letter_grade IN ('C+', 'C')         THEN 1 ELSE 0 END) AS "C range",
    SUM(CASE WHEN e.letter_grade = 'D'                  THEN 1 ELSE 0 END) AS "D",
    SUM(CASE WHEN e.letter_grade = 'F'                  THEN 1 ELSE 0 END) AS "F",
    COUNT(*)                                                               AS total
FROM enrollments e
JOIN course_offerings co  ON co.id  = e.offering_id
JOIN semesters        sem ON sem.id = co.semester_id
WHERE e.status = 'completed'
GROUP BY sem.id
ORDER BY sem.start_date;


-- ---------------------------------------------------------------------
-- Q17. Offerings with more than 40 students (not counting drops).
-- DEMONSTRATES: HAVING with a filtered count. The WHERE removes dropped
--     rows BEFORE counting; the HAVING keeps only the big groups.
-- ---------------------------------------------------------------------
SELECT
    sem.code                    AS semester,
    c.code || '-' || co.section AS offering,
    co.capacity,
    COUNT(e.id)                 AS students
FROM course_offerings co
JOIN courses     c   ON c.id   = co.course_id
JOIN semesters   sem ON sem.id = co.semester_id
JOIN enrollments e   ON e.offering_id = co.id
WHERE e.status <> 'dropped'
GROUP BY co.id
HAVING COUNT(e.id) > 40
ORDER BY students DESC;


-- ---------------------------------------------------------------------
-- Q18. Money collected per month.
-- DEMONSTRATES: grouping by a CALCULATED value. strftime('%Y-%m', date)
--     cuts a timestamp down to "year-month".
-- ---------------------------------------------------------------------
SELECT
    strftime('%Y-%m', paid_at)            AS month,
    COUNT(*)                              AS payments,
    printf('%.2f', SUM(amount) / 100.0)   AS collected_taka,
    printf('%.2f', AVG(amount) / 100.0)   AS average_payment_taka
FROM payments
GROUP BY strftime('%Y-%m', paid_at)
ORDER BY month;
