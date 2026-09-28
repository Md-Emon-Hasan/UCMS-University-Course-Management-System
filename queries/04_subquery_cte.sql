-- =====================================================================
-- 04_subquery_cte.sql  (Q24 - Q28)
-- Sub-queries and CTEs (Common Table Expressions).
--
-- A CTE is a named, temporary result you define at the top of a query:
--     WITH name AS (SELECT ...)
--     SELECT ... FROM name ...
-- It works like a view that exists only for this one query. It makes
-- long queries readable, because you can build them step by step.
--
-- CGPA (used below) = credit-weighted average of grade points:
--     SUM(grade_point * credits) / SUM(credits)
-- A 4-credit A counts more than a 1.5-credit A.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q24. Students whose CGPA is ABOVE the university average CGPA.
-- DEMONSTRATES: a CTE that is used twice: once to list students, and once
--     inside a scalar sub-query that computes the average.
-- ---------------------------------------------------------------------
WITH student_cgpa AS (
    SELECT
        e.student_id,
        ROUND(SUM(e.grade_point * c.credits) / SUM(c.credits), 2) AS cgpa,
        SUM(c.credits)                                            AS credits_earned
    FROM enrollments e
    JOIN course_offerings co ON co.id = e.offering_id
    JOIN courses          c  ON c.id  = co.course_id
    WHERE e.status = 'completed'
    GROUP BY e.student_id
)
SELECT
    s.student_code,
    s.first_name || ' ' || s.last_name              AS name,
    sc.cgpa,
    sc.credits_earned,
    (SELECT ROUND(AVG(cgpa), 2) FROM student_cgpa)  AS university_avg
FROM student_cgpa sc
JOIN students s ON s.id = sc.student_id
WHERE sc.cgpa > (SELECT AVG(cgpa) FROM student_cgpa)
ORDER BY sc.cgpa DESC
LIMIT 20;


-- ---------------------------------------------------------------------
-- Q25. Top-5 most popular courses (most enrollments over all semesters),
--      with their average grade.
-- DEMONSTRATES: a CTE for the counting step, then ORDER BY + LIMIT for
--     "top N". AVG ignores NULL grades (the current semester has none yet).
-- ---------------------------------------------------------------------
WITH course_popularity AS (
    SELECT
        co.course_id,
        COUNT(*)                        AS enrollments,
        COUNT(DISTINCT co.semester_id)  AS semesters_offered,
        ROUND(AVG(e.grade_point), 2)    AS avg_grade_point
    FROM enrollments e
    JOIN course_offerings co ON co.id = e.offering_id
    WHERE e.status <> 'dropped'
    GROUP BY co.course_id
)
SELECT c.code, c.title, cp.enrollments, cp.semesters_offered, cp.avg_grade_point
FROM course_popularity cp
JOIN courses c ON c.id = cp.course_id
ORDER BY cp.enrollments DESC, c.code
LIMIT 5;


-- ---------------------------------------------------------------------
-- Q26. Students who FAILED at least one course, and how many.
-- DEMONSTRATES: filtering with IN (sub-query). The inner query finds
--     "who failed", and the outer query shows details and counts.
-- ---------------------------------------------------------------------
SELECT
    s.student_code,
    s.first_name || ' ' || s.last_name AS name,
    (SELECT COUNT(*) FROM enrollments f
      WHERE f.student_id = s.id AND f.letter_grade = 'F') AS failed_courses,   -- correlated sub-query
    s.status
FROM students s
WHERE s.id IN (SELECT student_id FROM enrollments WHERE letter_grade = 'F')
ORDER BY failed_courses DESC, s.student_code;


-- ---------------------------------------------------------------------
-- Q27. The top payer: the student who has paid the MOST money in total.
-- DEMONSTRATES: comparing with = (SELECT MAX(...)) instead of LIMIT 1, so
--     that if two students tie for first place, BOTH are returned.
--     (LIMIT 1 would silently hide the other one.)
-- In the seed data this really happens: fees are fixed per department,
-- so every CSE student who paid in full in all 4 semesters paid exactly the
-- same total. Expect several rows. Change "=" to "LIMIT 1" and compare.
-- ---------------------------------------------------------------------
WITH paid_per_student AS (
    SELECT i.student_id, SUM(p.amount) AS total_paid, COUNT(p.id) AS payments
    FROM payments p
    JOIN invoices i ON i.id = p.invoice_id
    GROUP BY i.student_id
)
SELECT
    s.student_code,
    s.first_name || ' ' || s.last_name       AS name,
    d.code                                   AS dept,
    pps.payments,
    printf('%.2f', pps.total_paid / 100.0)   AS total_paid_taka
FROM paid_per_student pps
JOIN students    s ON s.id = pps.student_id
JOIN departments d ON d.id = s.department_id
WHERE pps.total_paid = (SELECT MAX(total_paid) FROM paid_per_student);


-- ---------------------------------------------------------------------
-- Q28. RECURSIVE CTE: the FULL prerequisite chain of CSE401
--      (Artificial Intelligence), at every depth.
-- DEMONSTRATES: WITH RECURSIVE. It has two parts joined by UNION:
--   1. the ANCHOR: the direct prerequisites of CSE401 (depth 1)
--   2. the RECURSIVE part: the prerequisites of the rows found so far
--      (depth + 1). SQLite repeats part 2 until it finds no new rows.
-- UNION (not UNION ALL) removes duplicate rows, and "depth < 10" is a
-- safety stop in case bad data ever contains a cycle.
--
-- The `path` column shows how each course was reached, e.g.
--   CSE401 <- CSE301 <- CSE201 <- CSE101
-- CSE401 needs BOTH CSE301 and CSE102 (a "diamond" in the tree).
-- ---------------------------------------------------------------------
WITH RECURSIVE prereq_chain (course_id, prerequisite_id, depth, path) AS (
    -- 1. anchor: direct prerequisites
    SELECT cp.course_id, cp.prerequisite_course_id, 1,
           c.code || ' <- ' || p.code
    FROM course_prerequisites cp
    JOIN courses c ON c.id = cp.course_id
    JOIN courses p ON p.id = cp.prerequisite_course_id
    WHERE c.code = 'CSE401'

    UNION

    -- 2. recursive step: prerequisites of the prerequisites
    SELECT cp.course_id, cp.prerequisite_course_id, pc.depth + 1,
           pc.path || ' <- ' || p.code
    FROM prereq_chain pc
    JOIN course_prerequisites cp ON cp.course_id = pc.prerequisite_id
    JOIN courses p ON p.id = cp.prerequisite_course_id
    WHERE pc.depth < 10
)
SELECT
    pc.depth,
    p.code  AS prerequisite_code,
    p.title AS prerequisite_title,
    p.level,
    pc.path
FROM prereq_chain pc
JOIN courses p ON p.id = pc.prerequisite_id
ORDER BY pc.depth, p.code;
