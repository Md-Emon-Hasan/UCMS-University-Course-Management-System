-- =====================================================================
-- 02_rebuild_circular_fk.sql
-- Adds the missing FK  departments.head_teacher_id -> teachers(id)
--
-- WHY THIS FILE EXISTS
--   departments and teachers point at each other (circular FK):
--     teachers.department_id     -> departments.id
--     departments.head_teacher_id -> teachers.id
--   In PostgreSQL/MySQL you would create both tables, then run
--   "ALTER TABLE departments ADD CONSTRAINT ... FOREIGN KEY ...".
--   SQLite's ALTER TABLE CANNOT add a constraint to an existing table.
--
-- THE SQLITE WAY: the official "12-step" table rebuild
--   (https://www.sqlite.org/lang_altertable.html#otheralter)
--   Build a new table with the correct definition, copy the data across,
--   drop the old table, then rename the new one to the old name.
--
-- Side note: SQLite actually allows a FK to a table that does not exist yet
-- (it only checks FKs when data changes). We still do the rebuild on purpose,
-- because this is the technique you need for ANY schema change that
-- ALTER TABLE cannot do (adding a CHECK, changing a column type, ...).
-- =====================================================================

-- Step 1: turn FK enforcement OFF. Otherwise "DROP TABLE departments"
-- would complain, because teachers/students/courses still reference it.
-- (This PRAGMA does nothing inside a transaction, so it must come first.)
PRAGMA foreign_keys = OFF;

-- Step 2: do everything in ONE transaction. If any step fails, nothing changes.
BEGIN TRANSACTION;

-- Steps 3-4: (would be: remember the indexes/triggers/views on the old
-- table). departments has none yet, only its UNIQUE constraints, which are
-- part of the CREATE TABLE below.

-- Step 5: create the NEW table with the correct definition (now with the FK).
CREATE TABLE departments_new (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    code             TEXT    NOT NULL UNIQUE,
    head_teacher_id  INTEGER NULL REFERENCES teachers(id) ON DELETE SET NULL,
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Step 6: copy every row across (list the columns explicitly, never SELECT *).
INSERT INTO departments_new (id, name, code, head_teacher_id, is_active, created_at, updated_at)
SELECT id, name, code, head_teacher_id, is_active, created_at, updated_at
FROM departments;

-- Step 7: drop the old table.
DROP TABLE departments;

-- Step 8: rename the new table to the old name. Other tables
-- (teachers, students, courses ...) reference departments BY NAME, so after
-- the rename their FKs point at the new table automatically.
ALTER TABLE departments_new RENAME TO departments;

-- Step 9: recreate indexes/triggers/views of the old table (none yet;
-- those are created later in 03_indexes.sql, 04_views.sql and 05_triggers.sql).

-- Step 10: check that no row breaks a FK. In this script the result rows
-- are discarded, so scripts/init_db.py runs the same check again from Python
-- and stops if it finds a problem.
PRAGMA foreign_key_check;

-- Step 11: commit the rebuild.
COMMIT;

-- Step 12: turn FK enforcement back ON.
PRAGMA foreign_keys = ON;
