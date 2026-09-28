-- =====================================================================
-- 05_window.sql  (Q29 - Q33)
-- Window functions: calculations ACROSS related rows WITHOUT collapsing them.
--
-- GROUP BY squashes each group into ONE row.
-- A window function keeps EVERY row and adds a value computed over its
-- "window" of related rows:
--     function(...) OVER (PARTITION BY <group> ORDER BY <order>)
--   PARTITION BY = which rows belong together (like GROUP BY, but no squashing)
--   ORDER BY     = the order inside each partition (needed for ranks, running sums, LAG)
--
-- Window functions run AFTER WHERE/GROUP BY, so to FILTER on their result
-- you must wrap the query in a CTE or sub-query (see Q30).
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q29. Rank the students inside ONE offering by grade point.
--      (We pick the past offering with the most students.)
-- DEMONSTRATES: RANK vs DENSE_RANK vs ROW_NUMBER on ties.
--   Grade points 4.0, 3.75, 3.75, 3.5 give:
--     ROW_NUMBER : 1, 2, 3, 4   (always unique)
--     RANK       : 1, 2, 2, 4   (a tie skips the next number)
--     DENSE_RANK : 1, 2, 2, 3   (a tie does not skip)
--   We rank by grade_point (not total_marks) because many students share
--   a grade point, so the ties are easy to see.
-- ---------------------------------------------------------------------
WITH biggest_offering AS (
    SELECT e.offering_id
    FROM enrollments e
    WHERE e.status = 'completed'
    GROUP BY e.offering_id
    ORDER BY COUNT(*) DESC, e.offering_id
    LIMIT 1
)
SELECT
    c.code || '-' || co.section                         AS offering,
    s.student_code,
    e.letter_grade,
    e.grade_point,
    e.total_marks,
    -- ROW_NUMBER needs a unique order, so ties are broken by marks, then code
    ROW_NUMBER() OVER (ORDER BY e.grade_point DESC, e.total_marks DESC, s.student_code) AS row_num,
    RANK()       OVER (ORDER BY e.grade_point DESC)     AS rank,
    DENSE_RANK() OVER (ORDER BY e.grade_point DESC)     AS dense_rank
FROM enrollments e
JOIN students         s  ON s.id  = e.student_id
JOIN course_offerings co ON co.id = e.offering_id
JOIN courses          c  ON c.id  = co.course_id
WHERE e.offering_id = (SELECT offering_id FROM biggest_offering)
ORDER BY row_num;


-- ---------------------------------------------------------------------
-- Q30. The top-3 students of EACH department by CGPA.
-- DEMONSTRATES: ROW_NUMBER() with PARTITION BY (the numbering restarts at
--     1 for each department), then filtering on it in an outer query.
--     "WHERE row_num <= 3" cannot go in the same SELECT, because window
--     values do not exist yet when WHERE runs.
-- ---------------------------------------------------------------------
WITH student_cgpa AS (
    SELECT
        e.student_id,
        ROUND(SUM(e.grade_point * c.credits) / SUM(c.credits), 2) AS cgpa
    FROM enrollments e
    JOIN course_offerings co ON co.id = e.offering_id
    JOIN courses          c  ON c.id  = co.course_id
    WHERE e.status = 'completed'
    GROUP BY e.student_id
),
ranked AS (
    SELECT
        d.code                               AS dept,
        s.student_code,
        s.first_name || ' ' || s.last_name   AS name,
        sc.cgpa,
        ROW_NUMBER() OVER (PARTITION BY d.id ORDER BY sc.cgpa DESC, s.student_code) AS row_num
    FROM student_cgpa sc
    JOIN students    s ON s.id = sc.student_id
    JOIN departments d ON d.id = s.department_id
)
SELECT dept, row_num AS position, student_code, name, cgpa
FROM ranked
WHERE row_num <= 3
ORDER BY dept, row_num;


-- ---------------------------------------------------------------------
-- Q31. Running (cumulative) total of money collected, day by day, in the
--      active semester.
-- DEMONSTRATES: SUM(...) OVER (ORDER BY ...), a running total. Each row
--     adds its own day to all the days before it. The inner query first
--     groups payments into one row per day.
-- ---------------------------------------------------------------------
WITH daily AS (
    SELECT date(p.paid_at) AS day, SUM(p.amount) AS collected
    FROM payments p
    JOIN invoices  i   ON i.id   = p.invoice_id
    JOIN semesters sem ON sem.id = i.semester_id
    WHERE sem.is_active = 1
    GROUP BY date(p.paid_at)
)
SELECT
    day,
    printf('%.2f', collected / 100.0)                              AS collected_taka,
    printf('%.2f', SUM(collected) OVER (ORDER BY day) / 100.0)     AS running_total_taka
FROM daily
ORDER BY day;


-- ---------------------------------------------------------------------
-- Q32. Semester-over-semester GPA change for each student.
-- DEMONSTRATES: LAG(value) OVER (PARTITION BY student ORDER BY semester)
--     returns the value from the PREVIOUS row of the same student, so we
--     can subtract and see whether they improved. The first semester has
--     no previous row, so LAG gives NULL there.
-- ---------------------------------------------------------------------
WITH semester_gpa AS (
    SELECT
        e.student_id,
        sem.code                                                  AS semester,
        sem.start_date,
        ROUND(SUM(e.grade_point * c.credits) / SUM(c.credits), 2) AS gpa
    FROM enrollments e
    JOIN course_offerings co  ON co.id  = e.offering_id
    JOIN courses          c   ON c.id   = co.course_id
    JOIN semesters        sem ON sem.id = co.semester_id
    WHERE e.status = 'completed'
    GROUP BY e.student_id, sem.id
)
SELECT
    s.student_code,
    sg.semester,
    sg.gpa,
    LAG(sg.gpa) OVER (PARTITION BY sg.student_id ORDER BY sg.start_date)            AS previous_gpa,
    ROUND(sg.gpa - LAG(sg.gpa) OVER (PARTITION BY sg.student_id ORDER BY sg.start_date), 2) AS change
FROM semester_gpa sg
JOIN students s ON s.id = sg.student_id
WHERE s.student_code IN (SELECT student_code FROM students ORDER BY id LIMIT 5)   -- first 5 students, to keep it short
ORDER BY s.student_code, sg.start_date;


-- ---------------------------------------------------------------------
-- Q33. Split students into 4 equal groups (quartiles) by CGPA.
-- DEMONSTRATES: NTILE(4) deals the ordered rows into 4 buckets of (almost)
--     equal size. Bucket 1 = top 25%. We then summarise each bucket.
-- ---------------------------------------------------------------------
WITH student_cgpa AS (
    SELECT
        e.student_id,
        SUM(e.grade_point * c.credits) / SUM(c.credits) AS cgpa
    FROM enrollments e
    JOIN course_offerings co ON co.id = e.offering_id
    JOIN courses          c  ON c.id  = co.course_id
    WHERE e.status = 'completed'
    GROUP BY e.student_id
),
bucketed AS (
    SELECT student_id, cgpa, NTILE(4) OVER (ORDER BY cgpa DESC) AS quartile
    FROM student_cgpa
)
SELECT
    quartile,
    COUNT(*)                AS students,
    ROUND(MIN(cgpa), 2)     AS lowest_cgpa,
    ROUND(MAX(cgpa), 2)     AS highest_cgpa,
    ROUND(AVG(cgpa), 2)     AS average_cgpa
FROM bucketed
GROUP BY quartile
ORDER BY quartile;
