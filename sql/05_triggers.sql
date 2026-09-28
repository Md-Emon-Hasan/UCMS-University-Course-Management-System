-- =====================================================================
-- 05_triggers.sql
-- A TRIGGER is SQL that runs automatically when a row is inserted, updated
-- or deleted. Inside a trigger:
--     NEW.col = the row's value AFTER the change  (INSERT, UPDATE)
--     OLD.col = the row's value BEFORE the change (UPDATE, DELETE)
--
-- BEFORE triggers can stop a change:  SELECT RAISE(ABORT, 'message') ...
-- RAISE(ABORT) undoes the current statement and returns the error to Python.
--
-- Contents
--   1. trg_<table>_updated_at          keep updated_at fresh (20 tables)
--   2. trg_enroll_count_ins/_upd/_del   keep course_offerings.enrolled_count in sync
--   3. trg_validate_marks_ins/_upd      marks_obtained <= max_marks
--   4. trg_payment_update_invoice       paid_amount + status after a payment
--   5. trg_audit_enrollments_*          audit log for enrollments
--   6. trg_audit_payments_*             audit log for payments
--   7. trg_no_room_conflict             one class per room per time slot
--   8. trg_no_teacher_conflict          one class per teacher per time slot
-- =====================================================================


-- =====================================================================
-- 1) updated_at triggers
--
-- SQLite has no "ON UPDATE CURRENT_TIMESTAMP" (MySQL has it), so after
-- every UPDATE we run a second, tiny UPDATE that sets updated_at.
--
-- The WHEN clause (NEW.updated_at = OLD.updated_at) means: only do it if
-- the statement did not already set updated_at. That also stops the
-- trigger's own UPDATE from triggering it again.
--
-- IMPORTANT side effect: the inner "UPDATE ... SET updated_at" is a real
-- UPDATE, so it also fires the OTHER AFTER UPDATE triggers of that table
-- (for example the audit trigger). Those triggers must ignore this
-- "timestamp only" update. See sections 2 and 5 for how they do it.
-- =====================================================================

CREATE TRIGGER trg_users_updated_at AFTER UPDATE ON users
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE users SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_departments_updated_at AFTER UPDATE ON departments
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE departments SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_teachers_updated_at AFTER UPDATE ON teachers
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE teachers SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_students_updated_at AFTER UPDATE ON students
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE students SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- student_profiles has no "id" column: its primary key is student_id
CREATE TRIGGER trg_student_profiles_updated_at AFTER UPDATE ON student_profiles
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE student_profiles SET updated_at = datetime('now') WHERE student_id = NEW.student_id;
END;

CREATE TRIGGER trg_semesters_updated_at AFTER UPDATE ON semesters
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE semesters SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_courses_updated_at AFTER UPDATE ON courses
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE courses SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_course_prerequisites_updated_at AFTER UPDATE ON course_prerequisites
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE course_prerequisites SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_rooms_updated_at AFTER UPDATE ON rooms
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE rooms SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_course_offerings_updated_at AFTER UPDATE ON course_offerings
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE course_offerings SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_class_schedules_updated_at AFTER UPDATE ON class_schedules
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE class_schedules SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_enrollments_updated_at AFTER UPDATE ON enrollments
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE enrollments SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_attendance_updated_at AFTER UPDATE ON attendance
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE attendance SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_assessments_updated_at AFTER UPDATE ON assessments
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE assessments SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_assessment_results_updated_at AFTER UPDATE ON assessment_results
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE assessment_results SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_fee_structures_updated_at AFTER UPDATE ON fee_structures
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE fee_structures SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_invoices_updated_at AFTER UPDATE ON invoices
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE invoices SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_invoice_items_updated_at AFTER UPDATE ON invoice_items
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE invoice_items SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_payments_updated_at AFTER UPDATE ON payments
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE payments SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_announcements_updated_at AFTER UPDATE ON announcements
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE announcements SET updated_at = datetime('now') WHERE id = NEW.id;
END;


-- =====================================================================
-- 2) enrolled_count sync
-- course_offerings.enrolled_count = number of enrollments with
-- status 'enrolled'. Storing a count is faster than COUNT(*) every time,
-- but it can drift out of date. Triggers keep it exact.
--
-- Bonus: the CHECK (enrolled_count <= capacity) on course_offerings now
-- guards capacity AT THE DATABASE LEVEL. If an insert would make the
-- count too big, the trigger's UPDATE fails and the whole INSERT is undone.
-- =====================================================================

-- A new 'enrolled' row takes one seat
CREATE TRIGGER trg_enroll_count_ins AFTER INSERT ON enrollments
FOR EACH ROW WHEN NEW.status = 'enrolled'
BEGIN
    UPDATE course_offerings
    SET enrolled_count = enrolled_count + 1
    WHERE id = NEW.offering_id;
END;

-- Status (or offering) changed: give back the old seat, take the new one.
-- "AFTER UPDATE OF status, offering_id" = only fire when these columns
-- are in the UPDATE's SET list.
CREATE TRIGGER trg_enroll_count_upd AFTER UPDATE OF status, offering_id ON enrollments
FOR EACH ROW
WHEN OLD.status IS NOT NEW.status OR OLD.offering_id IS NOT NEW.offering_id
BEGIN
    -- free the seat in the old offering (only if the old row held a seat)
    UPDATE course_offerings
    SET enrolled_count = enrolled_count - 1
    WHERE id = OLD.offering_id AND OLD.status = 'enrolled';

    -- take a seat in the new offering (only if the new row holds a seat)
    UPDATE course_offerings
    SET enrolled_count = enrolled_count + 1
    WHERE id = NEW.offering_id AND NEW.status = 'enrolled';
END;

-- A deleted 'enrolled' row frees its seat
CREATE TRIGGER trg_enroll_count_del AFTER DELETE ON enrollments
FOR EACH ROW WHEN OLD.status = 'enrolled'
BEGIN
    UPDATE course_offerings
    SET enrolled_count = enrolled_count - 1
    WHERE id = OLD.offering_id;
END;


-- =====================================================================
-- 3) Marks must not exceed the assessment's max_marks
-- A CHECK constraint can only look at its own row, so a rule that needs
-- another table (assessments.max_marks) must be a trigger.
-- A trigger fires on ONE event, so we need one for INSERT and one for UPDATE.
-- =====================================================================
CREATE TRIGGER trg_validate_marks_ins BEFORE INSERT ON assessment_results
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'marks exceed max_marks')
    WHERE NEW.marks_obtained > (SELECT max_marks FROM assessments WHERE id = NEW.assessment_id);
END;

CREATE TRIGGER trg_validate_marks_upd BEFORE UPDATE ON assessment_results
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'marks exceed max_marks')
    WHERE NEW.marks_obtained > (SELECT max_marks FROM assessments WHERE id = NEW.assessment_id);
END;


-- =====================================================================
-- 4) A payment updates its invoice
-- paid_amount is RECOMPUTED as the SUM of all payments (not "+= amount"),
-- so it is always correct, even if an earlier value was wrong.
-- If the sum goes above total_amount, the invoice CHECK
-- (paid_amount <= total_amount) fails and the payment INSERT is undone.
-- (In an UPDATE's SET list every expression sees the OLD row values,
-- so we repeat the SUM in the CASE instead of using paid_amount.)
-- =====================================================================
CREATE TRIGGER trg_payment_update_invoice AFTER INSERT ON payments
FOR EACH ROW
BEGIN
    UPDATE invoices
    SET paid_amount = (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE invoice_id = NEW.invoice_id),
        status = CASE
            WHEN (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE invoice_id = NEW.invoice_id) >= total_amount
                THEN 'paid'
            WHEN (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE invoice_id = NEW.invoice_id) > 0
                THEN 'partial'
            ELSE 'unpaid'
        END
    WHERE id = NEW.invoice_id;
END;


-- =====================================================================
-- 5) Audit log for enrollments
-- json_object('key', value, ...) builds a JSON text like
--     {"id":5,"status":"enrolled",...}
-- changed_by comes from the one-row _audit_actor table, which Python fills
-- at the start of every write transaction (app/database.py -> set_actor).
--
-- The UPDATE trigger only logs when at least one AUDITED column really
-- changed. This skips the "timestamp only" UPDATE made by
-- trg_enrollments_updated_at (otherwise every change would be logged twice).
-- We compare with IS NOT instead of <> because NULL <> 5 is NULL
-- ("unknown"), not true, while NULL IS NOT 5 is true.
--
-- (A first version used WHEN NEW.updated_at = OLD.updated_at. That failed
-- when the change happened in the same second the row was written: the
-- timestamp did not change, so the duplicate got through. See LEARNING_NOTES.)
-- =====================================================================
CREATE TRIGGER trg_audit_enrollments_ins AFTER INSERT ON enrollments
FOR EACH ROW
BEGIN
    INSERT INTO audit_logs (table_name, record_id, action, old_data, new_data, changed_by)
    VALUES (
        'enrollments', NEW.id, 'INSERT',
        NULL,
        json_object('id', NEW.id, 'student_id', NEW.student_id, 'offering_id', NEW.offering_id,
                    'status', NEW.status, 'enrolled_at', NEW.enrolled_at,
                    'total_marks', NEW.total_marks, 'grade_point', NEW.grade_point,
                    'letter_grade', NEW.letter_grade, 'dropped_at', NEW.dropped_at),
        (SELECT user_id FROM _audit_actor WHERE id = 1)
    );
END;

CREATE TRIGGER trg_audit_enrollments_upd AFTER UPDATE ON enrollments
FOR EACH ROW
WHEN OLD.student_id   IS NOT NEW.student_id
  OR OLD.offering_id  IS NOT NEW.offering_id
  OR OLD.status       IS NOT NEW.status
  OR OLD.enrolled_at  IS NOT NEW.enrolled_at
  OR OLD.total_marks  IS NOT NEW.total_marks
  OR OLD.grade_point  IS NOT NEW.grade_point
  OR OLD.letter_grade IS NOT NEW.letter_grade
  OR OLD.dropped_at   IS NOT NEW.dropped_at
BEGIN
    INSERT INTO audit_logs (table_name, record_id, action, old_data, new_data, changed_by)
    VALUES (
        'enrollments', NEW.id, 'UPDATE',
        json_object('id', OLD.id, 'student_id', OLD.student_id, 'offering_id', OLD.offering_id,
                    'status', OLD.status, 'enrolled_at', OLD.enrolled_at,
                    'total_marks', OLD.total_marks, 'grade_point', OLD.grade_point,
                    'letter_grade', OLD.letter_grade, 'dropped_at', OLD.dropped_at),
        json_object('id', NEW.id, 'student_id', NEW.student_id, 'offering_id', NEW.offering_id,
                    'status', NEW.status, 'enrolled_at', NEW.enrolled_at,
                    'total_marks', NEW.total_marks, 'grade_point', NEW.grade_point,
                    'letter_grade', NEW.letter_grade, 'dropped_at', NEW.dropped_at),
        (SELECT user_id FROM _audit_actor WHERE id = 1)
    );
END;

CREATE TRIGGER trg_audit_enrollments_del AFTER DELETE ON enrollments
FOR EACH ROW
BEGIN
    INSERT INTO audit_logs (table_name, record_id, action, old_data, new_data, changed_by)
    VALUES (
        'enrollments', OLD.id, 'DELETE',
        json_object('id', OLD.id, 'student_id', OLD.student_id, 'offering_id', OLD.offering_id,
                    'status', OLD.status, 'enrolled_at', OLD.enrolled_at,
                    'total_marks', OLD.total_marks, 'grade_point', OLD.grade_point,
                    'letter_grade', OLD.letter_grade, 'dropped_at', OLD.dropped_at),
        NULL,
        (SELECT user_id FROM _audit_actor WHERE id = 1)
    );
END;


-- =====================================================================
-- 6) Audit log for payments (same pattern as section 5)
-- =====================================================================
CREATE TRIGGER trg_audit_payments_ins AFTER INSERT ON payments
FOR EACH ROW
BEGIN
    INSERT INTO audit_logs (table_name, record_id, action, old_data, new_data, changed_by)
    VALUES (
        'payments', NEW.id, 'INSERT',
        NULL,
        json_object('id', NEW.id, 'invoice_id', NEW.invoice_id, 'amount', NEW.amount,
                    'method', NEW.method, 'transaction_ref', NEW.transaction_ref,
                    'paid_at', NEW.paid_at, 'received_by', NEW.received_by),
        (SELECT user_id FROM _audit_actor WHERE id = 1)
    );
END;

CREATE TRIGGER trg_audit_payments_upd AFTER UPDATE ON payments
FOR EACH ROW
WHEN OLD.invoice_id      IS NOT NEW.invoice_id
  OR OLD.amount          IS NOT NEW.amount
  OR OLD.method          IS NOT NEW.method
  OR OLD.transaction_ref IS NOT NEW.transaction_ref
  OR OLD.paid_at         IS NOT NEW.paid_at
  OR OLD.received_by     IS NOT NEW.received_by
BEGIN
    INSERT INTO audit_logs (table_name, record_id, action, old_data, new_data, changed_by)
    VALUES (
        'payments', NEW.id, 'UPDATE',
        json_object('id', OLD.id, 'invoice_id', OLD.invoice_id, 'amount', OLD.amount,
                    'method', OLD.method, 'transaction_ref', OLD.transaction_ref,
                    'paid_at', OLD.paid_at, 'received_by', OLD.received_by),
        json_object('id', NEW.id, 'invoice_id', NEW.invoice_id, 'amount', NEW.amount,
                    'method', NEW.method, 'transaction_ref', NEW.transaction_ref,
                    'paid_at', NEW.paid_at, 'received_by', NEW.received_by),
        (SELECT user_id FROM _audit_actor WHERE id = 1)
    );
END;

CREATE TRIGGER trg_audit_payments_del AFTER DELETE ON payments
FOR EACH ROW
BEGIN
    INSERT INTO audit_logs (table_name, record_id, action, old_data, new_data, changed_by)
    VALUES (
        'payments', OLD.id, 'DELETE',
        json_object('id', OLD.id, 'invoice_id', OLD.invoice_id, 'amount', OLD.amount,
                    'method', OLD.method, 'transaction_ref', OLD.transaction_ref,
                    'paid_at', OLD.paid_at, 'received_by', OLD.received_by),
        NULL,
        (SELECT user_id FROM _audit_actor WHERE id = 1)
    );
END;


-- =====================================================================
-- 7) No room double-booking
-- Two time ranges [s1, e1) and [s2, e2) overlap when  s1 < e2 AND e1 > s2.
-- (Touching ranges like 09:00-10:00 and 10:00-11:00 do NOT overlap.)
--
-- Only classes of the SAME semester can clash: rooms are reused every
-- semester. Cancelled offerings do not block a room.
-- =====================================================================
CREATE TRIGGER trg_no_room_conflict BEFORE INSERT ON class_schedules
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'room conflict: this room is already booked at that time')
    WHERE EXISTS (
        SELECT 1
        FROM class_schedules cs
        JOIN course_offerings co ON co.id = cs.offering_id
        WHERE cs.room_id     = NEW.room_id
          AND cs.day_of_week = NEW.day_of_week
          AND NEW.start_time < cs.end_time
          AND NEW.end_time   > cs.start_time
          AND co.status     <> 'cancelled'
          AND co.semester_id = (SELECT semester_id FROM course_offerings WHERE id = NEW.offering_id)
    );
END;


-- =====================================================================
-- 8) No teacher double-booking
-- Find the teacher of the NEW offering, then look for any other class of
-- that teacher, in the same semester and on the same day, whose time
-- overlaps.
-- =====================================================================
CREATE TRIGGER trg_no_teacher_conflict BEFORE INSERT ON class_schedules
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'teacher conflict: this teacher already has a class at that time')
    WHERE EXISTS (
        SELECT 1
        FROM class_schedules cs
        JOIN course_offerings co ON co.id = cs.offering_id
        JOIN course_offerings new_co ON new_co.id = NEW.offering_id
        WHERE co.teacher_id  = new_co.teacher_id
          AND co.semester_id = new_co.semester_id
          AND co.status     <> 'cancelled'
          AND cs.day_of_week = NEW.day_of_week
          AND NEW.start_time < cs.end_time
          AND NEW.end_time   > cs.start_time
    );
END;
