-- =====================================================================
-- 06_reports.sql  (Q34 - Q40)
-- Real reports that combine everything: views, CTEs, window functions,
-- date maths and JSON.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q34. Full transcript of the demo student, with semester GPA and the
--      CGPA shown on every row.
-- DEMONSTRATES: reading from a VIEW (v_student_transcript), plus two
--     window SUMs:
--       OVER (PARTITION BY semester) -> totals per semester  -> semester GPA
--       OVER ()                      -> totals over ALL rows -> CGPA
--     Empty OVER () means "the window is the whole result".
-- ---------------------------------------------------------------------
SELECT
    t.semester_code,
    t.course_code,
    t.course_title,
    t.credits,
    t.total_marks,
    t.letter_grade,
    t.grade_point,
    ROUND(SUM(t.grade_point * t.credits) OVER (PARTITION BY t.semester_id)
        / SUM(t.credits) OVER (PARTITION BY t.semester_id), 2)          AS semester_gpa,
    ROUND(SUM(t.grade_point * t.credits) OVER ()
        / SUM(t.credits) OVER (), 2)                                     AS cgpa
FROM v_student_transcript t
JOIN students s ON s.id = t.student_id
JOIN users    u ON u.id = s.user_id
WHERE u.email = 'student@ucms.edu'
ORDER BY t.semester_start, t.course_code;


-- ---------------------------------------------------------------------
-- Q35. Low-attendance list: students below 75% in a course of the
--      ACTIVE semester, worst first.
-- DEMONSTRATES: using a view (v_attendance_percentage) as a building block
--     and filtering on its computed column.
-- ---------------------------------------------------------------------
SELECT
    s.student_code,
    s.first_name || ' ' || s.last_name   AS student,
    c.code || '-' || co.section          AS offering,
    v.present_count || '/' || v.total_classes AS attended,
    v.attendance_percent
FROM v_attendance_percentage v
JOIN students         s   ON s.id   = v.student_id
JOIN course_offerings co  ON co.id  = v.offering_id
JOIN courses          c   ON c.id   = co.course_id
JOIN semesters        sem ON sem.id = co.semester_id
WHERE sem.is_active = 1
  AND v.attendance_percent < 75
ORDER BY v.attendance_percent, s.student_code;


-- ---------------------------------------------------------------------
-- Q36. Grade distribution of the whole university: count and percentage
--      per letter grade, from best to worst.
-- DEMONSTRATES: a percentage-of-total with SUM(COUNT(*)) OVER (), a window
--     function applied to an AGGREGATE. It runs after GROUP BY, so it can
--     sum the group counts.
-- ---------------------------------------------------------------------
SELECT
    letter_grade,
    grade_point,
    COUNT(*)                                            AS students,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)  AS percent
FROM enrollments
WHERE status = 'completed'
GROUP BY letter_grade, grade_point
ORDER BY grade_point DESC;


-- ---------------------------------------------------------------------
-- Q37. Overdue invoices with how many days late and how much is due,
--      most overdue first.
-- DEMONSTRATES: a view that already does the date maths
--     (julianday(now) - julianday(due_date)), filtered and sorted.
-- ---------------------------------------------------------------------
SELECT
    invoice_no,
    student_code,
    name,
    printf('%.2f', total_amount / 100.0) AS total_taka,
    printf('%.2f', paid_amount / 100.0)  AS paid_taka,
    printf('%.2f', due_amount / 100.0)   AS due_taka,
    due_date,
    days_overdue
FROM v_outstanding_dues
WHERE days_overdue > 0
ORDER BY days_overdue DESC, due_amount DESC
LIMIT 25;


-- ---------------------------------------------------------------------
-- Q38. Teacher workload in the active semester, busiest first, with each
--      teacher's share of all students taught.
-- DEMONSTRATES: a view (v_teacher_workload) plus a window SUM for "share
--     of total".
-- ---------------------------------------------------------------------
SELECT
    w.teacher_name,
    d.code                     AS dept,
    w.course_count,
    w.total_credits,
    w.total_students,
    ROUND(100.0 * w.total_students / SUM(w.total_students) OVER (), 1) AS share_of_students_percent
FROM v_teacher_workload w
JOIN departments d   ON d.id   = w.department_id
JOIN semesters   sem ON sem.id = w.semester_id
WHERE sem.is_active = 1
ORDER BY w.total_students DESC, w.teacher_name;


-- ---------------------------------------------------------------------
-- Q39. Room utilization: booked hours per week in the active semester,
--      as a percentage of the available teaching time.
--      Available = 5 days (Sun-Thu) x 10 hours (08:00-18:00) = 50 hours.
-- DEMONSTRATES: time maths on TEXT times. julianday('2000-01-01 09:30')
--     turns a date+time into a day number with a fraction, so
--     (end - start) * 24 = hours. The fixed date is only a placeholder.
--     LEFT JOIN keeps rooms that are never booked (0 hours).
-- ---------------------------------------------------------------------
SELECT
    r.building,
    r.room_number,
    r.room_type,
    r.capacity,
    COUNT(cs.id)                                           AS weekly_classes,
    ROUND(COALESCE(SUM((julianday('2000-01-01 ' || cs.end_time)
                      - julianday('2000-01-01 ' || cs.start_time)) * 24), 0), 1) AS booked_hours,
    ROUND(100.0 * COALESCE(SUM((julianday('2000-01-01 ' || cs.end_time)
                      - julianday('2000-01-01 ' || cs.start_time)) * 24), 0) / 50, 1) AS utilization_percent
FROM rooms r
LEFT JOIN class_schedules cs
       ON cs.room_id = r.id
      AND cs.offering_id IN (SELECT co.id FROM course_offerings co
                             JOIN semesters sem ON sem.id = co.semester_id
                             WHERE sem.is_active = 1)        -- in ON, so unbooked rooms stay
GROUP BY r.id
ORDER BY utilization_percent DESC, r.building, r.room_number;


-- ---------------------------------------------------------------------
-- Q40. Full audit history of ONE enrollment: every INSERT/UPDATE/DELETE,
--      who did it, and how the status changed.
-- DEMONSTRATES: reading JSON text with json_extract(). The audit triggers
--     stored old/new rows as JSON; '$.status' means "the status key".
-- We use the demo student's most recent enrollment. Seeded rows only have
-- an INSERT. Drop or grade it in the app and run this again to see new
-- UPDATE rows appear.
-- ---------------------------------------------------------------------
SELECT
    a.changed_at,
    a.action,
    u.email                                 AS changed_by,
    json_extract(a.old_data, '$.status')    AS old_status,
    json_extract(a.new_data, '$.status')    AS new_status,
    json_extract(a.new_data, '$.letter_grade') AS new_grade,
    a.new_data
FROM audit_logs a
LEFT JOIN users u ON u.id = a.changed_by       -- LEFT: changed_by may be NULL
WHERE a.table_name = 'enrollments'
  AND a.record_id = (
        SELECT MAX(e.id) FROM enrollments e
        JOIN students s  ON s.id = e.student_id
        JOIN users    su ON su.id = s.user_id
        WHERE su.email = 'student@ucms.edu')
ORDER BY a.id;
