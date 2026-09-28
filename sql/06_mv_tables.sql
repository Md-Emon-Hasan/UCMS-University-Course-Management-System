-- =====================================================================
-- 06_mv_tables.sql
-- "Materialized view" = a query result SAVED into a real table.
--
-- A normal VIEW runs its SELECT every time (always fresh, but slow for heavy
-- maths). PostgreSQL has CREATE MATERIALIZED VIEW + REFRESH, but SQLite
-- does not. We copy the idea by hand:
--   * a normal table holds the pre-calculated numbers
--   * a Python function recalculates it on demand:
--       app/services/report_service.py -> refresh_department_performance()
--
-- Trade-off: reading is instant, but the data is only as fresh as the last
-- refresh (see refreshed_at).
--
-- Columns follow the spec: one row per (department, semester).
--   avg_gpa        average grade_point of completed enrollments
--   pass_rate      % of completed enrollments with grade_point >= 2.0
--   total_students number of distinct students with a completed course
-- =====================================================================
CREATE TABLE mv_department_performance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id   INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    semester_id     INTEGER NOT NULL REFERENCES semesters(id)   ON DELETE CASCADE,
    avg_gpa         REAL    NULL,
    pass_rate       REAL    NULL,
    total_students  INTEGER NOT NULL DEFAULT 0,
    refreshed_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_mv_dept_semester UNIQUE (department_id, semester_id)
);
