"""
API tests: the real FastAPI app, called through TestClient (no server needed).

    1. Role matrix     every endpoint: no token -> 401, wrong role -> 403, right role -> passes
    2. Ownership       a student asking for ANOTHER student's data -> 403 (same for teachers)
    3. Auth            login, wrong password, disabled account, bad/expired token
    4. Happy paths     one real flow per area: departments, students, enrollment,
                       attendance, marks and grades, billing, schedules, lists
    5. Seeded smoke    the full demo data set: every demo login, every dashboard, every list

Every test (except part 5) gets its own fresh database with the small world
from tests/factory.py.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app import config
from app.main import app
from tests.factory import (TEST_PASSWORD, count, day, make_enrollment, make_fee, make_invoice, make_offering,
                           make_result, make_schedule, make_user)

ALL = {"admin", "teacher", "student", "accountant"}
MONEY = {"admin", "accountant"}
STAFF = {"admin", "teacher"}

# ---------------------------------------------------------------------------
# 1) Role matrix: (method, path, roles that may call it)
# {names} in the path are filled from the world ids.
# ---------------------------------------------------------------------------
ENDPOINTS = [
    ("GET", "/api/auth/me", ALL),
    ("GET", "/api/dashboard/stats", ALL),
    ("GET", "/api/departments", ALL),
    ("POST", "/api/departments", {"admin"}),
    ("GET", "/api/departments/{cse_id}", ALL),
    ("PATCH", "/api/departments/{cse_id}", {"admin"}),
    ("GET", "/api/teachers", {"admin"}),
    ("POST", "/api/teachers", {"admin"}),
    ("GET", "/api/teachers/{teacher_id}", STAFF),                 # admin, or the teacher themself
    ("PATCH", "/api/teachers/{teacher_id}", {"admin"}),
    ("GET", "/api/teachers/{teacher_id}/workload", STAFF),
    ("GET", "/api/students", {"admin"}),
    ("POST", "/api/students", {"admin"}),
    ("GET", "/api/students/{student_id}", {"admin", "student"}),   # admin, or the student themself
    ("PATCH", "/api/students/{student_id}", {"admin"}),
    ("GET", "/api/students/{student_id}/transcript", {"admin", "student"}),
    ("GET", "/api/students/{student_id}/dues", {"admin", "student"}),
    ("GET", "/api/students/{student_id}/attendance", {"admin", "student"}),
    ("GET", "/api/courses", ALL),
    ("POST", "/api/courses", {"admin"}),
    ("GET", "/api/courses/{course_id}", ALL),
    ("PATCH", "/api/courses/{course_id}", {"admin"}),
    ("GET", "/api/courses/{course_id}/prerequisite-tree", ALL),
    ("POST", "/api/courses/{course_id}/prerequisites", {"admin"}),
    ("GET", "/api/rooms", ALL),
    ("POST", "/api/rooms", {"admin"}),
    ("GET", "/api/rooms/{room_id}", ALL),
    ("PATCH", "/api/rooms/{room_id}", {"admin"}),
    ("GET", "/api/semesters", ALL),
    ("POST", "/api/semesters", {"admin"}),
    ("GET", "/api/semesters/active", ALL),
    ("GET", "/api/semesters/{semester_id}", ALL),
    ("PATCH", "/api/semesters/{semester_id}/activate", {"admin"}),
    ("POST", "/api/semesters/{semester_id}/close", {"admin"}),
    ("GET", "/api/offerings", STAFF),
    ("POST", "/api/offerings", {"admin"}),
    ("GET", "/api/offerings/{offering_id}", STAFF),
    ("PATCH", "/api/offerings/{offering_id}", {"admin"}),
    ("GET", "/api/offerings/{offering_id}/roster", STAFF),
    ("POST", "/api/offerings/{offering_id}/schedules", {"admin"}),
    ("GET", "/api/schedules/weekly", ALL),
    ("DELETE", "/api/schedules/9999", {"admin"}),
    ("POST", "/api/enrollments", {"admin", "student"}),
    ("GET", "/api/enrollments", {"admin", "teacher", "student"}),
    ("GET", "/api/enrollments/eligibility", {"admin", "student"}),
    ("PATCH", "/api/enrollments/9999/drop", {"admin", "student"}),        # 9999: allowed roles get 404
    ("POST", "/api/enrollments/9999/finalize-grade", STAFF),
    ("POST", "/api/offerings/{offering_id}/attendance", STAFF),
    ("GET", "/api/offerings/{offering_id}/attendance", STAFF),
    ("GET", "/api/offerings/{offering_id}/attendance-report", STAFF),
    ("POST", "/api/assessments", STAFF),
    ("GET", "/api/offerings/{offering_id}/assessments", STAFF),
    ("POST", "/api/assessments/9999/results", STAFF),
    ("GET", "/api/offerings/{offering_id}/gradebook", STAFF),
    ("GET", "/api/fee-structures", MONEY),
    ("POST", "/api/fee-structures", MONEY),
    ("POST", "/api/invoices/generate", MONEY),
    ("GET", "/api/invoices", MONEY),
    ("POST", "/api/payments", MONEY),
    ("GET", "/api/payments", MONEY),
    ("GET", "/api/announcements", ALL),
    ("POST", "/api/announcements", {"admin"}),
    ("GET", "/api/audit-logs", {"admin"}),
    ("GET", "/api/reports/grade-distribution", STAFF),
    ("GET", "/api/reports/department-performance", {"admin"}),
    ("POST", "/api/reports/department-performance/refresh", {"admin"}),
    ("GET", "/api/reports/collection-summary", MONEY),
    ("GET", "/api/reports/low-attendance", STAFF),
]


def call(client: TestClient, method: str, path: str, headers: dict | None = None):
    """Send a request. Write requests get an empty JSON body: enough to reach the role check."""
    body = {} if method in ("POST", "PATCH") else None
    return client.request(method, path, headers=headers or {}, json=body)


@pytest.mark.parametrize("method, path, allowed", ENDPOINTS, ids=[f"{m} {p}" for m, p, _ in ENDPOINTS])
def test_role_matrix(client, world, auth, method, path, allowed):
    """
    For one endpoint: no token must give 401, a role that is not allowed 403,
    and an allowed role anything else (200, 201, or 422 for our empty body).
    """
    url = path.format(**world)
    actual = {"no token": call(client, method, url).status_code}
    for role in sorted(ALL):
        status = call(client, method, url, auth(role)).status_code
        actual[role] = "passes" if status not in (401, 403) else status

    expected = {"no token": 401}
    for role in sorted(ALL):
        expected[role] = "passes" if role in allowed else 403
    assert actual == expected


def test_every_api_route_is_in_the_matrix():
    """If someone adds an endpoint, this test reminds them to add it to ENDPOINTS too."""
    def shape(path: str) -> str:
        # "/api/departments/{department_id}", "/api/departments/{cse_id}" and "/api/departments/9999"
        # all become "/api/departments/{}", so they can be compared
        return "/".join("{}" if part.startswith("{") or part.isdigit() else part for part in path.split("/"))

    in_matrix = {(method, shape(path)) for method, path, _ in ENDPOINTS}
    routes = {(method, shape(route.path)) for route in app.routes if route.path.startswith("/api")
              for method in getattr(route, "methods", set())}
    not_needed = {
        ("POST", "/api/auth/login"),        # public on purpose
        ("GET", "/api/invoices/{}"),        # any role may call it; test_student_cannot_open_another_students_invoice
    }
    assert sorted(routes - in_matrix - not_needed) == []


# ---------------------------------------------------------------------------
# 2) Ownership: the right role is not enough, it must also be YOUR data
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/students/{other_student_id}",
    "/api/students/{other_student_id}/transcript",
    "/api/students/{other_student_id}/dues",
    "/api/students/{other_student_id}/attendance",
    "/api/enrollments?student_id={other_student_id}",
])
def test_student_cannot_read_another_student(client, world, auth, path):
    """The same URL works for the owner, and gives 403 to another student."""
    other = client.get(path.format(**world), headers=auth("student"))
    owner = client.get(path.format(**world), headers=auth("other_student"))
    assert (other.status_code, owner.status_code) == (403, 200)
    assert "own" in other.json()["detail"]


def test_student_cannot_open_another_students_invoice(client, conn, world, auth):
    invoice = make_invoice(conn, world["other_student_id"], world["semester_id"], 1_000_00)
    assert client.get(f"/api/invoices/{invoice}", headers=auth("student")).status_code == 403
    assert client.get(f"/api/invoices/{invoice}", headers=auth("other_student")).status_code == 200
    assert client.get(f"/api/invoices/{invoice}", headers=auth("accountant")).status_code == 200


def test_student_cannot_drop_another_students_course(client, conn, world, auth):
    enrollment = make_enrollment(conn, world["other_student_id"], world["offering_id"])
    response = client.patch(f"/api/enrollments/{enrollment}/drop", headers=auth("student"))
    assert response.status_code == 403
    assert count(conn, "enrollments", "id = ? AND status = 'enrolled'", (enrollment,)) == 1


def test_student_eligibility_is_always_their_own(client, conn, world, auth):
    """
    For a student, ?student_id= is ignored and replaced by their own id, so
    asking about someone else simply returns your own list (no data leaks).
    """
    make_enrollment(conn, world["other_student_id"], world["offering_id"])
    items = client.get(f"/api/enrollments/eligibility?student_id={world['other_student_id']}",
                       headers=auth("student")).json()["items"]
    assert items[0]["eligible"] is True           # the OTHER student is enrolled; this one is not


def test_student_can_only_enroll_themself(client, world, auth):
    """A student_id in the body is ignored for students: the token decides who enrolls."""
    response = client.post("/api/enrollments", headers=auth("student"),
                           json={"offering_id": world["offering_id"], "student_id": world["other_student_id"]})
    assert response.status_code == 201
    assert response.json()["student_id"] == world["student_id"]


@pytest.mark.parametrize("path", ["/api/offerings/{offering_id}/roster", "/api/offerings/{offering_id}/gradebook",
                                  "/api/offerings/{offering_id}/attendance-report", "/api/offerings/{offering_id}"])
def test_teacher_cannot_manage_another_teachers_offering(client, world, auth, path):
    assert client.get(path.format(**world), headers=auth("other_teacher")).status_code == 403
    assert client.get(path.format(**world), headers=auth("teacher")).status_code == 200


def test_teacher_cannot_see_another_teachers_workload(client, world, auth):
    url = f"/api/teachers/{world['teacher_id']}/workload"
    assert client.get(url, headers=auth("other_teacher")).status_code == 403
    assert client.get(url, headers=auth("teacher")).status_code == 200


def test_teacher_cannot_grade_another_teachers_student(client, conn, world, auth):
    enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    response = client.post(f"/api/enrollments/{enrollment}/finalize-grade", headers=auth("other_teacher"))
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 3) Authentication
# ---------------------------------------------------------------------------
def test_login_returns_a_working_token(client, world):
    response = client.post("/api/auth/login", json={"email": "student@test.edu", "password": TEST_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert (body["role"], body["user"]["student_id"]) == ("student", world["student_id"])
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == "student@test.edu"


def test_login_email_ignores_case(client, world):
    """users.email is COLLATE NOCASE, so the lookup matches whatever the case."""
    response = client.post("/api/auth/login", json={"email": "Student@TEST.edu", "password": TEST_PASSWORD})
    assert response.status_code == 200


def test_login_records_last_login(client, conn, world):
    client.post("/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD})
    assert count(conn, "users", "id = ? AND last_login_at IS NOT NULL", (world["admin_user_id"],)) == 1


@pytest.mark.parametrize("email, password", [("student@test.edu", "wrong-password"), ("nobody@test.edu", TEST_PASSWORD)])
def test_wrong_login_gives_the_same_message(client, world, email, password):
    """Wrong password and unknown email look identical, so nobody can test which emails exist."""
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert (response.status_code, response.json()["detail"]) == (401, "Invalid email or password")


def test_disabled_account_cannot_log_in_or_use_old_tokens(client, conn, world, auth):
    headers = auth("student")
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (world["student_user_id"],))
    login = client.post("/api/auth/login", json={"email": "student@test.edu", "password": TEST_PASSWORD})
    assert login.status_code == 403
    assert client.get("/api/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize("token", [
    "not-a-jwt",
    jwt.encode({"sub": "1", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
               "some-other-secret", algorithm="HS256"),                                   # wrong signature
    "EXPIRED",
])
def test_bad_tokens_are_rejected(client, world, token):
    if token == "EXPIRED":
        token = jwt.encode({"sub": str(world["admin_user_id"]), "role": "admin",
                            "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                           config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert (response.status_code, response.json()["detail"]) == (401, "Invalid or expired token")


# ---------------------------------------------------------------------------
# 4) Happy paths and error formats
# ---------------------------------------------------------------------------
def test_create_department_and_error_formats(client, auth):
    admin = auth("admin")
    created = client.post("/api/departments", headers=admin, json={"name": "Physics", "code": "PHY"})
    assert created.status_code == 201 and created.json()["code"] == "PHY"

    # UNIQUE constraint -> 409, with the message attached to the right form field
    duplicate = client.post("/api/departments", headers=admin, json={"name": "Physics 2", "code": "PHY"})
    assert duplicate.status_code == 409
    assert duplicate.json()["errors"] == {"code": "A department with this code already exists"}

    # Pydantic validation -> 422 with one message per field
    invalid = client.post("/api/departments", headers=admin, json={"name": "P", "code": "phy"})
    assert invalid.status_code == 422
    assert set(invalid.json()["errors"]) == {"name", "code"}

    # extra="forbid": a typo in a field name is an error, not silently ignored
    typo = client.post("/api/departments", headers=admin, json={"name": "Chemistry", "code": "CHE", "cdoe": "X"})
    assert typo.status_code == 422 and "cdoe" in typo.json()["errors"]


NEW_STUDENT = {
    "email": "nadia.rahman@test.edu", "password": "Password123!", "student_code": "CSE26999",
    "first_name": "Nadia", "last_name": "Rahman", "admission_date": "2026-01-10",
    "profile": {"date_of_birth": "2005-03-04", "gender": "female", "guardian_name": "Karim Rahman",
                "guardian_phone": "01711111111", "guardian_relation": "Father"},
}


def test_create_student_writes_three_tables(client, conn, world, auth):
    response = client.post("/api/students", headers=auth("admin"), json=NEW_STUDENT | {"department_id": world["cse_id"]})
    assert response.status_code == 201
    student_id = response.json()["id"]
    assert count(conn, "users", "email = ?", ("nadia.rahman@test.edu",)) == 1
    assert count(conn, "student_profiles", "student_id = ?", (student_id,)) == 1


def test_create_student_is_all_or_nothing(client, conn, world, auth):
    """
    The users row is inserted FIRST, then the students row fails (duplicate
    student_code). The transaction must remove the new users row again.
    """
    taken_code = conn.execute("SELECT student_code FROM students WHERE id = ?", (world["student_id"],)).fetchone()[0]
    users_before = count(conn, "users")
    response = client.post("/api/students", headers=auth("admin"),
                           json=NEW_STUDENT | {"department_id": world["cse_id"], "student_code": taken_code})
    assert response.status_code == 409
    assert response.json()["errors"] == {"student_code": "This student code is already used"}
    assert count(conn, "users") == users_before
    assert count(conn, "users", "email = ?", ("nadia.rahman@test.edu",)) == 0


def test_enroll_drop_and_audit_through_the_api(client, conn, world, auth):
    student = auth("student")
    eligibility = client.get("/api/enrollments/eligibility", headers=student).json()
    assert [(item["id"], item["eligible"]) for item in eligibility["items"]] == [(world["offering_id"], True)]

    enrolled = client.post("/api/enrollments", headers=student, json={"offering_id": world["offering_id"]})
    assert enrolled.status_code == 201
    enrollment_id = enrolled.json()["id"]

    again = client.post("/api/enrollments", headers=student, json={"offering_id": world["offering_id"]})
    assert again.status_code == 400 and "Already enrolled" in again.json()["detail"]

    dropped = client.patch(f"/api/enrollments/{enrollment_id}/drop", headers=student)
    assert dropped.json()["status"] == "dropped"

    # The triggers wrote the history, with the student as the actor
    logs = client.get(f"/api/audit-logs?table_name=enrollments&record_id={enrollment_id}&sort=id",
                      headers=auth("admin")).json()["items"]
    assert [(log["action"], log["changed_by"]) for log in logs] == [
        ("INSERT", world["student_user_id"]), ("UPDATE", world["student_user_id"])]
    assert logs[1]["old_data"]["status"] == "enrolled" and logs[1]["new_data"]["status"] == "dropped"


def test_full_offering_gives_a_clear_message(client, conn, world, auth):
    tiny = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], capacity=1, section="T")
    make_enrollment(conn, world["other_student_id"], tiny)
    response = client.post("/api/enrollments", headers=auth("admin"),
                           json={"offering_id": tiny, "student_id": world["student_id"]})
    assert (response.status_code, response.json()["detail"]) == (400, "This offering is full (1/1)")


def test_attendance_save_is_an_upsert(client, conn, world, auth):
    """Saving the same date twice UPDATES the rows (ON CONFLICT DO UPDATE) instead of failing."""
    enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    url = f"/api/offerings/{world['offering_id']}/attendance"
    for status in ("absent", "late"):
        body = {"class_date": day(-1), "records": [{"enrollment_id": enrollment, "status": status}]}
        assert client.post(url, headers=auth("teacher"), json=body).json()["saved"] == 1
    assert count(conn, "attendance", "enrollment_id = ?", (enrollment,)) == 1
    assert conn.execute("SELECT status FROM attendance WHERE enrollment_id = ?", (enrollment,)).fetchone()[0] == "late"


def test_attendance_date_must_be_inside_the_semester(client, conn, world, auth):
    enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    body = {"class_date": day(-400), "records": [{"enrollment_id": enrollment, "status": "present"}]}
    response = client.post(f"/api/offerings/{world['offering_id']}/attendance", headers=auth("teacher"), json=body)
    assert response.status_code == 400 and "class_date" in response.json()["errors"]


def test_marks_then_final_grade(client, conn, world, auth):
    teacher = auth("teacher")
    enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    quiz, assignment, midterm, final = world["assessment_ids"]

    too_high = client.post(f"/api/assessments/{quiz}/results", headers=teacher,
                           json={"results": [{"enrollment_id": enrollment, "marks_obtained": 25}]})
    assert too_high.status_code == 400
    assert too_high.json()["errors"] == {"results.0.marks_obtained": "Marks 25 exceed max_marks 20"}

    for assessment, marks in ((quiz, 18), (assignment, 16), (midterm, 24), (final, 30)):
        response = client.post(f"/api/assessments/{assessment}/results", headers=teacher,
                               json={"results": [{"enrollment_id": enrollment, "marks_obtained": marks}]})
        assert response.status_code == 200

    # 18/20*10 + 16/20*20 + 24/30*30 + 30/40*40 = 9 + 16 + 24 + 30 = 79 -> A (3.75)
    graded = client.post(f"/api/enrollments/{enrollment}/finalize-grade", headers=teacher).json()
    assert (graded["total_marks"], graded["letter_grade"], graded["grade_point"]) == (79.0, "A", 3.75)

    transcript = client.get(f"/api/students/{world['student_id']}/transcript", headers=auth("student")).json()
    assert transcript["cgpa"] == 3.75


def test_billing_flow_money_in_paisa_and_taka(client, conn, world, auth):
    accountant = auth("accountant")
    fee = client.post("/api/fee-structures", headers=accountant,
                      json={"semester_id": world["semester_id"], "fee_type": "tuition", "amount": 45000.50})
    assert fee.status_code == 201 and fee.json()["amount"] == 4_500_050      # taka in, paisa stored

    make_enrollment(conn, world["student_id"], world["offering_id"])
    generated = client.post("/api/invoices/generate", headers=accountant, json={"semester_id": world["semester_id"]})
    assert generated.json()["created"] == 1
    invoice_id = generated.json()["invoice_ids"][0]

    over = client.post("/api/payments", headers=accountant,
                       json={"invoice_id": invoice_id, "amount": 50000, "method": "cash"})
    assert over.status_code == 400 and "amount" in over.json()["errors"]

    paid = client.post("/api/payments", headers=accountant,
                       json={"invoice_id": invoice_id, "amount": 20000.25, "method": "bkash", "transaction_ref": "BK-9"})
    assert paid.status_code == 201
    invoice = paid.json()["invoice"]
    assert (invoice["status"], invoice["paid_amount"], invoice["due_amount_taka"]) == ("partial", 2_000_025, "25000.25")

    reused = client.post("/api/payments", headers=accountant,
                         json={"invoice_id": invoice_id, "amount": 1, "method": "bkash", "transaction_ref": "BK-9"})
    assert reused.status_code == 409 and "transaction_ref" in reused.json()["errors"]


def test_schedule_clash_comes_back_as_409(client, conn, world, auth):
    make_schedule(conn, world["offering_id"], world["room_id"], 2, "11:00", "12:30")
    other = make_offering(conn, world["course_id"], world["semester_id"], world["other_teacher_id"], section="B")
    response = client.post(f"/api/offerings/{other}/schedules", headers=auth("admin"),
                           json={"room_id": world["room_id"], "day_of_week": 2, "start_time": "12:00", "end_time": "13:00"})
    assert response.status_code == 409
    assert response.json()["detail"] == "room conflict: this room is already booked at that time"


def test_pagination_and_safe_sorting(client, conn, world, auth):
    admin = auth("admin")
    for code in ("MTH101", "MTH102", "MTH103"):
        conn.execute("INSERT INTO courses (department_id, code, title, credits, level) VALUES (?, ?, 'Maths', 3, 1)",
                     (world["cse_id"], code))
    page = client.get("/api/courses?limit=2&page=2&sort=code&order=desc&search=MTH", headers=admin).json()
    assert (page["total"], page["pages"], page["page"], page["limit"]) == (3, 2, 2, 2)
    assert [course["code"] for course in page["items"]] == ["MTH101"]

    # An attack in the sort column is NOT pasted into SQL: it is not on the whitelist, so the default is used
    attack = client.get("/api/courses?sort=id;DROP TABLE users", headers=admin)
    assert attack.status_code == 200
    assert count(conn, "users") > 0

    assert client.get("/api/courses?limit=500", headers=admin).status_code == 422      # limit is at most 200


def test_frontend_is_served(client):
    assert "text/html" in client.get("/").headers["content-type"]
    assert client.get("/pages/login.html").status_code == 200
    assert client.get("/static/js/api.js").status_code == 200


# ---------------------------------------------------------------------------
# 5) Smoke tests on the full demo data (built once; these tests only read)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def seeded_client(seeded_db_path):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(config, "DB_PATH", seeded_db_path)
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture(scope="module")
def demo_headers(seeded_client) -> dict:
    """Log in once as each demo account (this only updates last_login_at)."""
    headers = {}
    for role in sorted(ALL):
        response = seeded_client.post("/api/auth/login", json={"email": f"{role}@ucms.edu", "password": "Password123!"})
        assert response.status_code == 200, response.text
        headers[role] = {"Authorization": f"Bearer {response.json()['access_token']}"}
    return headers


@pytest.mark.parametrize("role", sorted(ALL))
def test_demo_dashboards(seeded_client, demo_headers, role):
    stats = seeded_client.get("/api/dashboard/stats", headers=demo_headers[role])
    assert stats.status_code == 200
    assert stats.json()["role"] == role and stats.json()["semester"] is not None


@pytest.mark.parametrize("path", [
    "/api/departments", "/api/teachers", "/api/students", "/api/courses", "/api/rooms", "/api/semesters",
    "/api/offerings", "/api/enrollments", "/api/fee-structures", "/api/invoices", "/api/payments",
    "/api/announcements", "/api/audit-logs", "/api/schedules/weekly", "/api/courses/1/prerequisite-tree",
    "/api/reports/grade-distribution", "/api/reports/department-performance",
    "/api/reports/collection-summary", "/api/reports/low-attendance",
])
def test_demo_admin_lists(seeded_client, demo_headers, path):
    response = seeded_client.get(path, headers=demo_headers["admin"])
    assert response.status_code == 200, response.text
    body = response.json()
    if "total" in body:                              # paged lists always have rows in the demo data
        assert body["total"] > 0


def test_demo_student_sees_real_data(seeded_client, demo_headers):
    me = seeded_client.get("/api/auth/me", headers=demo_headers["student"]).json()
    student = demo_headers["student"]
    transcript = seeded_client.get(f"/api/students/{me['student_id']}/transcript", headers=student).json()
    assert transcript["courses_completed"] > 0
    eligibility = seeded_client.get("/api/enrollments/eligibility", headers=student).json()
    assert len(eligibility["items"]) > 0
    assert seeded_client.get(f"/api/students/{me['student_id'] + 1}", headers=student).status_code == 403
