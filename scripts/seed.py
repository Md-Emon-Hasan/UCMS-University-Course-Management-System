"""
Fill the database with realistic, deterministic demo data.

Usage (from the project folder):
    python scripts/seed.py            # seed an empty database (creates it if missing)
    python scripts/seed.py --reset    # delete everything first, then seed

Deterministic: random.Random(42) + Faker seed 42. The same run date always
gives the same data. Dates are calculated relative to TODAY, so the "active"
semester always has an open registration window, whenever you run it.

Order of work (parents before children, because of foreign keys):
    users -> departments -> teachers -> department heads -> students -> profiles
    -> rooms -> courses -> prerequisites -> semesters -> fee structures
    -> for each semester, oldest first:
         offerings -> schedules -> assessments -> enrollments -> results -> attendance
    -> invoices -> invoice items -> payments -> announcements
    -> refresh mv_department_performance

Everything runs in ONE transaction: if any step fails, nothing is saved.

Realism rules (from the spec):
    * ~15% of students have low attendance
    * ~20% of invoices end up unpaid, partial or overdue
    * some offerings are full, some are nearly empty
    * past-semester enrollments are all 'completed' with grades
    * marks follow a normal (bell-shaped) distribution
    * students only take a course after PASSING its prerequisites
"""

import argparse
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from faker import Faker  # noqa: E402
from passlib.context import CryptContext  # noqa: E402

from app import config  # noqa: E402
from app.database import fetch_value, get_connection, set_actor, transaction  # noqa: E402
from app.services.grading_service import PASS_GRADE_POINT, marks_to_gpa  # noqa: E402
from app.services.report_service import refresh_department_performance  # noqa: E402
from scripts.init_db import init_database, list_tables  # noqa: E402
from scripts.reset_db import delete_database_files  # noqa: E402


# =============================================================================
# Random generators (seeded, so every run gives the same data)
# =============================================================================
SEED = 42
rng = random.Random(SEED)
fake = Faker("en_US")
fake.seed_instance(SEED)

TODAY = date.today()
DEMO_PASSWORD = "Password123!"


# =============================================================================
# Fixed reference data
# =============================================================================
DEPARTMENTS = [
    ("CSE", "Computer Science and Engineering"),
    ("EEE", "Electrical and Electronic Engineering"),
    ("BBA", "Business Administration"),
    ("ENG", "English"),
    ("MATH", "Mathematics"),
]

# 12 courses per department: 3 per level (1-4). Each entry: (title, credits)
# 1.5-credit courses are labs (they are scheduled in lab rooms).
COURSE_CATALOGUE = {
    "CSE": [
        ("Structured Programming", 3), ("Discrete Mathematics", 3), ("Computer Fundamentals Lab", 1.5),
        ("Data Structures", 3), ("Database Systems", 3), ("Digital Logic Design", 3),
        ("Algorithms", 3), ("Advanced Database Systems", 3), ("Computer Architecture", 3),
        ("Artificial Intelligence", 3), ("Distributed Databases", 3), ("Embedded Systems", 4),
    ],
    "EEE": [
        ("Electrical Circuits I", 3), ("Physics for Engineers", 3), ("Electrical Workshop Lab", 1.5),
        ("Electrical Circuits II", 3), ("Electromagnetic Fields", 3), ("Electronics I", 3),
        ("Power Systems I", 3), ("Antennas and Propagation", 3), ("Electronics II", 3),
        ("Power Systems II", 3), ("Microwave Engineering", 3), ("VLSI Design", 4),
    ],
    "BBA": [
        ("Principles of Management", 3), ("Principles of Accounting", 3), ("Business Communication", 1.5),
        ("Organizational Behaviour", 3), ("Cost Accounting", 3), ("Microeconomics", 3),
        ("Human Resource Management", 3), ("Management Accounting", 3), ("Macroeconomics", 3),
        ("Strategic Management", 3), ("Auditing", 3), ("International Business", 4),
    ],
    "ENG": [
        ("Introduction to Literature", 3), ("English Grammar", 3), ("Language Lab", 1.5),
        ("Romantic Poetry", 3), ("Phonetics and Phonology", 3), ("Academic Writing", 3),
        ("Victorian Literature", 3), ("Sociolinguistics", 3), ("Creative Writing", 3),
        ("Modern Drama", 3), ("Applied Linguistics", 3), ("Research Methods", 4),
    ],
    "MATH": [
        ("Calculus I", 3), ("Linear Algebra", 3), ("Mathematical Software Lab", 1.5),
        ("Calculus II", 3), ("Abstract Algebra", 3), ("Probability", 3),
        ("Real Analysis", 3), ("Ring and Field Theory", 3), ("Statistics", 3),
        ("Complex Analysis", 3), ("Galois Theory", 3), ("Stochastic Processes", 4),
    ],
}

# Prerequisite pattern inside each department, using positions 0..11 in the list above.
# (course position, prerequisite position). 8 per department -> 40 in total.
#   level 2: pos 3 needs 0, pos 4 needs 1, pos 5 has none
#   level 3: pos 6 needs 3, pos 7 needs 4, pos 8 needs 5
#   level 4: pos 9 needs 6, pos 10 needs 7, pos 11 needs 8
PREREQ_PATTERN = [(3, 0), (4, 1), (6, 3), (7, 4), (8, 5), (9, 6), (10, 7), (11, 8)]
# One extra "diamond" for the course-tree demo: CSE Artificial Intelligence also needs Discrete Mathematics
EXTRA_PREREQS = [("CSE", 9, 1)]

ROOMS = (
    [("Academic Building A", f"1{n:02d}", cap, "lecture")
     for n, cap in enumerate([40, 50, 60, 60, 80, 100, 120, 50], start=1)]
    + [("Academic Building B", f"2{n:02d}", cap, "lecture")
       for n, cap in enumerate([40, 45, 50, 55, 60, 70], start=1)]
    + [("Academic Building B", "301", 30, "seminar"), ("Academic Building B", "302", 35, "seminar")]
    + [("Science Lab Complex", f"L{n}", cap, "lab") for n, cap in enumerate([50, 50, 60, 60], start=1)]
)

MALE_NAMES = [
    "Rahim", "Karim", "Tanvir", "Arif", "Hasan", "Mahmud", "Nayeem", "Rakib", "Sabbir", "Fahim",
    "Imran", "Shakil", "Sohel", "Tareq", "Zahid", "Farhan", "Rafiq", "Jamil", "Mizan", "Ashraf",
    "Nafis", "Rifat", "Siam", "Tahmid", "Anik", "Rashed", "Ovi", "Sajid", "Mehedi", "Ahnaf",
]
FEMALE_NAMES = [
    "Nusrat", "Farzana", "Sadia", "Tasnim", "Sumaiya", "Fatema", "Ayesha", "Mim", "Jannat", "Sharmin",
    "Rumana", "Tahmina", "Nabila", "Lamia", "Anika", "Maliha", "Rafia", "Sabrina", "Afsana", "Shirin",
    "Tania", "Nadia", "Samira", "Israt", "Mahjabin", "Raisa", "Tasfia", "Humaira", "Zarin", "Orpa",
]
LAST_NAMES = [
    "Rahman", "Hossain", "Ahmed", "Islam", "Chowdhury", "Khan", "Uddin", "Alam", "Sarker", "Das",
    "Roy", "Talukder", "Haque", "Kabir", "Siddique", "Karim", "Bhuiyan", "Majumder", "Saha", "Paul",
    "Barua", "Chakraborty", "Mondal", "Sikder", "Hasan", "Mahmud", "Sheikh", "Akter", "Molla", "Biswas",
]
CITIES = ["Dhaka", "Chattogram", "Khulna", "Rajshahi", "Sylhet", "Barishal", "Rangpur",
          "Mymensingh", "Cumilla", "Gazipur", "Narayanganj", "Bogura"]
AREAS = ["Dhanmondi", "Mirpur", "Uttara", "Mohammadpur", "Banani", "Bashundhara", "Agrabad",
         "Zindabazar", "Sonadanga", "Shaheb Bazar", "Nasirabad", "Khilgaon"]
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
PHONE_PREFIXES = ["013", "014", "015", "016", "017", "018", "019"]

# Weekly time slots (every class ends by 18:00 so it fits the routine grid).
TIME_SLOTS = [("08:00", "09:20"), ("09:30", "10:50"), ("11:00", "12:20"),
              ("12:30", "13:50"), ("14:00", "15:20"), ("15:30", "16:50")]
# Each offering meets twice a week on the same slot. 0 = Sunday ... 4 = Thursday
DAY_PAIRS = [(0, 2), (1, 3), (2, 4), (0, 3), (1, 4)]

# (title, type, max_marks, weight_percent, due = days after semester start)
# The weights MUST add up to exactly 100 (checked in main()).
ASSESSMENT_PLAN = [
    ("Quiz 1", "quiz", 20, 10, 14),
    ("Assignment 1", "assignment", 50, 20, 35),
    ("Midterm Exam", "midterm", 30, 30, 56),
    ("Final Exam", "final", 60, 40, 105),
]

OFFERINGS_PER_DEPT_PER_SEMESTER = 6        # 5 depts x 6 x 4 semesters = 120 offerings
SEMESTER_GAP_DAYS = 122                     # distance between two semester starts
SEMESTER_LENGTH_DAYS = 118
ACTIVE_SEMESTER_STARTED_DAYS_AGO = 60       # the active semester is ~8 weeks in
PAST_TEACHING_DAYS = 77                     # attendance is recorded for 11 weeks of each past semester
INVOICE_DUE_DAYS = 75                       # invoice due date = semester start + 75 days

PAYMENT_METHODS = ["bkash", "bank", "cash", "nagad", "card"]
PAYMENT_METHOD_WEIGHTS = [35, 25, 20, 12, 8]


# =============================================================================
# Small helpers
# =============================================================================
def to_paisa(taka: float) -> int:
    """Convert taka (1500.50) to integer paisa (150050). Money is never stored as REAL."""
    return int(round(taka * 100))


def ts(day: date, hour: int = 10, minute: int = 0) -> str:
    """Build an ISO timestamp text 'YYYY-MM-DD HH:MM:SS'."""
    return f"{day.isoformat()} {hour:02d}:{minute:02d}:00"


def random_day(start: date, end: date) -> date:
    """A random date between start and end (both included)."""
    span = max(0, (end - start).days)
    return start + timedelta(days=rng.randint(0, span))


def random_time_on(day: date) -> str:
    """A random office-hours timestamp on the given day."""
    return ts(day, rng.randint(9, 17), rng.randint(0, 59))


def phone_number() -> str:
    """A Bangladeshi mobile number like 01712345678."""
    return rng.choice(PHONE_PREFIXES) + fake.numerify("########")


def db_day_of_week(day: date) -> int:
    """Our day numbering: 0 = Sunday ... 6 = Saturday (Python's weekday() has Monday = 0)."""
    return (day.weekday() + 1) % 7


def semester_code_and_name(start: date) -> tuple[str, str]:
    """Season from the start month: Jan-Apr Spring, May-Aug Summer, Sep-Dec Fall."""
    if start.month <= 4:
        season, short = "Spring", "SPR"
    elif start.month <= 8:
        season, short = "Summer", "SUM"
    else:
        season, short = "Fall", "FAL"
    return f"{short}{start.year % 100:02d}", f"{season} {start.year}"


def weighted_pick(items: list, weights: list[float]):
    """Pick ONE item at random; items with a bigger weight are picked more often."""
    return rng.choices(items, weights=weights, k=1)[0]


def insert(conn, sql: str, params: tuple) -> int:
    """Run one INSERT and return the new row id."""
    return conn.execute(sql, params).lastrowid


# =============================================================================
# Step 1: users, departments, teachers, students
# =============================================================================
def seed_staff_users(conn, password_hash: str) -> dict:
    """Create the admin and accountant accounts. Returns their user ids."""
    staff = {"admin": [], "accountant": []}
    accounts = [
        ("admin@ucms.edu", "admin"), ("registrar@ucms.edu", "admin"), ("it.admin@ucms.edu", "admin"),
        ("accountant@ucms.edu", "accountant"), ("accounts.office@ucms.edu", "accountant"),
        ("cashier@ucms.edu", "accountant"),
    ]
    for email, role in accounts:
        user_id = insert(
            conn,
            "INSERT INTO users (email, password_hash, role, last_login_at) VALUES (?, ?, ?, ?)",
            (email, password_hash, role, random_time_on(TODAY - timedelta(days=rng.randint(0, 10)))),
        )
        staff[role].append(user_id)
    return staff


def seed_departments(conn) -> dict[str, int]:
    """Create the 5 departments (heads are set after the teachers exist)."""
    dept_ids = {}
    for code, name in DEPARTMENTS:
        dept_ids[code] = insert(conn, "INSERT INTO departments (name, code) VALUES (?, ?)", (name, code))
    return dept_ids


def make_unique_email(first: str, last: str, used: set[str], domain: str = "ucms.edu") -> str:
    """firstname.lastname@domain, adding a number if the address is already taken."""
    base = f"{first}.{last}".lower()
    email, n = f"{base}@{domain}", 2
    while email in used:
        email, n = f"{base}{n}@{domain}", n + 1
    used.add(email)
    return email


def seed_teachers(conn, dept_ids: dict[str, int], password_hash: str) -> list[dict]:
    """
    Create 6 teachers per department (30 in total).
    The first CSE teacher is the demo account teacher@ucms.edu.
    """
    designations = ["professor", "associate_professor", "assistant_professor",
                    "assistant_professor", "lecturer", "lecturer"]
    teachers, used_emails, number = [], {"teacher@ucms.edu"}, 1

    for code, _name in DEPARTMENTS:
        for position, designation in enumerate(designations):
            is_demo = code == "CSE" and position == 0
            female = rng.random() < 0.4
            first = rng.choice(FEMALE_NAMES if female else MALE_NAMES)
            last = rng.choice(LAST_NAMES)
            email = "teacher@ucms.edu" if is_demo else make_unique_email(first, last, used_emails)

            user_id = insert(
                conn,
                "INSERT INTO users (email, password_hash, role, last_login_at) VALUES (?, ?, 'teacher', ?)",
                (email, password_hash, random_time_on(TODAY - timedelta(days=rng.randint(0, 15)))),
            )
            hired = random_day(date(2008, 1, 1), date(2023, 12, 31))
            teacher_id = insert(
                conn,
                """INSERT INTO teachers (user_id, department_id, employee_code, first_name, last_name,
                                         phone, designation, hired_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, dept_ids[code], f"EMP{number:03d}", first, last, phone_number(),
                 designation, hired.isoformat()),
            )
            teachers.append({"id": teacher_id, "user_id": user_id, "dept": code, "status": "active",
                             "is_demo": is_demo, "is_head": position == 0})
            number += 1

    # A few teachers are not active any more (never the demo teacher or a department head)
    candidates = [t for t in teachers if not t["is_demo"] and not t["is_head"]]
    for teacher, status in zip(rng.sample(candidates, 3), ["on_leave", "on_leave", "resigned"]):
        teacher["status"] = status
        conn.execute("UPDATE teachers SET status = ? WHERE id = ?", (status, teacher["id"]))
        if status == "resigned":
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (teacher["user_id"],))

    # Department heads: the professor of each department (this uses the circular FK)
    for teacher in teachers:
        if teacher["is_head"]:
            conn.execute("UPDATE departments SET head_teacher_id = ? WHERE id = ?",
                         (teacher["id"], dept_ids[teacher["dept"]]))
    return teachers


def seed_students(conn, dept_ids: dict[str, int], password_hash: str, first_semester_start: date,
                  active_semester_start: date) -> list[dict]:
    """
    Create 60 students per department (300 in total) and one profile each (1:1).

    Each student also gets two hidden "personality" numbers used later:
        ability     - their typical marks (normal distribution, mean 64)
        attend_rate - chance of attending a class (15% of students are low)
    """
    students = []
    for code, _name in DEPARTMENTS:
        for seq in range(1, 61):
            is_demo = code == "CSE" and seq == 1
            is_new = seq == 60        # one brand-new admission per department (no enrollments yet)

            if is_new:
                admitted = active_semester_start - timedelta(days=10)
            else:
                admitted = random_day(first_semester_start - timedelta(days=400),
                                      first_semester_start - timedelta(days=30))
            student_code = f"{code}{admitted.year % 100:02d}{seq:03d}"
            email = "student@ucms.edu" if is_demo else f"{student_code.lower()}@student.ucms.edu"

            gender = "female" if rng.random() < 0.45 else "male"
            first = rng.choice(FEMALE_NAMES if gender == "female" else MALE_NAMES)
            last = rng.choice(LAST_NAMES)

            user_id = insert(
                conn,
                "INSERT INTO users (email, password_hash, role, last_login_at) VALUES (?, ?, 'student', ?)",
                (email, password_hash,
                 random_time_on(TODAY - timedelta(days=rng.randint(0, 30))) if rng.random() < 0.7 else None),
            )
            student_id = insert(
                conn,
                """INSERT INTO students (user_id, department_id, student_code, first_name, last_name,
                                         admission_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, dept_ids[code], student_code, first, last, admitted.isoformat()),
            )

            # 1:1 profile. The guardian is usually the father (same last name).
            relation = weighted_pick(["Father", "Mother", "Uncle", "Brother"], [60, 30, 5, 5])
            guardian_first = rng.choice(FEMALE_NAMES if relation == "Mother" else MALE_NAMES)
            city_index = rng.randrange(len(CITIES))
            conn.execute(
                """INSERT INTO student_profiles (student_id, date_of_birth, gender, blood_group,
                        address_line, city, postal_code, guardian_name, guardian_phone, guardian_relation)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (student_id,
                 random_day(date(2000, 1, 1), date(2006, 12, 31)).isoformat(),
                 gender,
                 rng.choice(BLOOD_GROUPS) if rng.random() < 0.9 else None,
                 f"House {rng.randint(1, 120)}, Road {rng.randint(1, 30)}, {AREAS[city_index % len(AREAS)]}",
                 CITIES[city_index],
                 fake.numerify("####"),
                 f"{guardian_first} {last}",
                 phone_number(),
                 relation),
            )

            low_attendance = (not is_demo) and rng.random() < 0.15
            students.append({
                "id": student_id, "user_id": user_id, "dept": code, "code": student_code,
                "status": "active", "is_demo": is_demo, "is_new": is_new,
                "ability": 74.0 if is_demo else min(97.0, max(25.0, rng.gauss(64, 11))),
                "attend_rate": rng.uniform(0.40, 0.68) if low_attendance else rng.uniform(0.80, 0.97),
            })

    # A few students are not active any more (never the demo student or a new admission)
    candidates = [s for s in students if not s["is_demo"] and not s["is_new"]]
    statuses = ["suspended"] * 7 + ["dropped_out"] * 5 + ["graduated"] * 3
    for student, status in zip(rng.sample(candidates, len(statuses)), statuses):
        student["status"] = status
        conn.execute("UPDATE students SET status = ? WHERE id = ?", (status, student["id"]))
        if status == "dropped_out":
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (student["user_id"],))
    return students


# =============================================================================
# Step 2: rooms, courses, prerequisites, semesters, fee structures
# =============================================================================
def seed_rooms(conn) -> list[dict]:
    """Create the 20 rooms."""
    rooms = []
    for building, number, capacity, room_type in ROOMS:
        room_id = insert(conn, "INSERT INTO rooms (building, room_number, capacity, room_type) VALUES (?, ?, ?, ?)",
                         (building, number, capacity, room_type))
        rooms.append({"id": room_id, "capacity": capacity, "type": room_type})
    return rooms


def seed_courses(conn, dept_ids: dict[str, int]) -> tuple[list[dict], dict[int, list[int]]]:
    """
    Create the 60 courses and ~40 prerequisite links.

    Returns:
        (courses, prereqs) where prereqs maps course_id -> [prerequisite course ids]
    """
    courses, by_position = [], {}
    for code, _name in DEPARTMENTS:
        for position, (title, credits) in enumerate(COURSE_CATALOGUE[code]):
            level = position // 3 + 1
            course_code = f"{code}{level}0{position % 3 + 1}"          # e.g. CSE201
            course_id = insert(
                conn,
                """INSERT INTO courses (department_id, code, title, description, credits, level)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (dept_ids[code], course_code, title, fake.sentence(nb_words=14), credits, level),
            )
            course = {"id": course_id, "dept": code, "code": course_code, "credits": credits,
                      "level": level, "is_lab": credits == 1.5}
            courses.append(course)
            by_position[(code, position)] = course

    prereqs: dict[int, list[int]] = {c["id"]: [] for c in courses}
    links = [(code, course_pos, prereq_pos) for code, _ in DEPARTMENTS for course_pos, prereq_pos in PREREQ_PATTERN]
    links += EXTRA_PREREQS
    for code, course_pos, prereq_pos in links:
        course_id = by_position[(code, course_pos)]["id"]
        prereq_id = by_position[(code, prereq_pos)]["id"]
        conn.execute("INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES (?, ?)",
                     (course_id, prereq_id))
        prereqs[course_id].append(prereq_id)
    return courses, prereqs


def seed_semesters(conn) -> list[dict]:
    """
    Create 4 semesters: 3 past and 1 active, oldest first.
    The active one started ~8 weeks ago and its registration (add/drop) window is still open.
    """
    active_start = TODAY - timedelta(days=ACTIVE_SEMESTER_STARTED_DAYS_AGO)
    semesters = []
    for index in range(4):
        start = active_start - timedelta(days=(3 - index) * SEMESTER_GAP_DAYS)
        is_active = index == 3
        code, name = semester_code_and_name(start)
        reg_start = start - timedelta(days=21)
        reg_end = TODAY + timedelta(days=14) if is_active else start + timedelta(days=7)
        semester_id = insert(
            conn,
            """INSERT INTO semesters (name, code, start_date, end_date, registration_start,
                                      registration_end, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, code, start.isoformat(), (start + timedelta(days=SEMESTER_LENGTH_DAYS)).isoformat(),
             reg_start.isoformat(), reg_end.isoformat(), 1 if is_active else 0),
        )
        semesters.append({
            "id": semester_id, "code": code, "start": start, "reg_start": reg_start,
            "is_active": is_active,
            # attendance is recorded up to (not including) this day
            "attendance_until": TODAY if is_active else start + timedelta(days=PAST_TEACHING_DAYS),
        })
    return semesters


def seed_fee_structures(conn, semesters: list[dict], dept_ids: dict[str, int]) -> dict:
    """
    5 fee rows per semester (20 in total): global tuition, exam and library,
    plus department-specific tuition for CSE and EEE (these override the global one).

    Returns:
        fees[semester_id] = {"tuition": {None: (id, amount), "CSE": (...)}, "exam": ..., "library": ...}
    """
    plan = [
        (None, "tuition", 48500.00), (None, "exam", 2750.50), (None, "library", 1200.00),
        ("CSE", "tuition", 56250.50), ("EEE", "tuition", 53000.00),
    ]
    fees = {}
    for semester in semesters:
        fees[semester["id"]] = {"tuition": {}, "exam": {}, "library": {}}
        for dept_code, fee_type, taka in plan:
            amount = to_paisa(taka)
            fee_id = insert(
                conn,
                "INSERT INTO fee_structures (semester_id, department_id, fee_type, amount) VALUES (?, ?, ?, ?)",
                (semester["id"], dept_ids[dept_code] if dept_code else None, fee_type, amount),
            )
            fees[semester["id"]][fee_type][dept_code] = (fee_id, amount)
    return fees


# =============================================================================
# Step 3: one semester of teaching (offerings -> ... -> attendance)
# =============================================================================
def plan_offerings(semester: dict, courses: list[dict], prereqs: dict, students: list[dict],
                   passed: dict[int, set], teachers: list[dict]) -> list[dict]:
    """
    Decide which courses are offered this semester, based on DEMAND.

    For each department we count how many students may take each course
    (prerequisites passed, course not passed yet), then offer the 6 most
    wanted courses. If fewer than 6 courses are wanted, popular courses get
    a second section.
    """
    offerings = []
    for dept_code, _name in DEPARTMENTS:
        dept_students = [s for s in students if s["dept"] == dept_code and takes_classes(s, semester)]
        dept_courses = [c for c in courses if c["dept"] == dept_code]

        demand = {}
        for course in dept_courses:
            demand[course["id"]] = sum(1 for s in dept_students if is_eligible(s, course, prereqs, passed))
        wanted = [c for c in dept_courses if demand[c["id"]] > 0]
        wanted.sort(key=lambda c: (-demand[c["id"]], rng.random()))

        chosen = wanted[:OFFERINGS_PER_DEPT_PER_SEMESTER]
        extra = 0
        while len(chosen) < OFFERINGS_PER_DEPT_PER_SEMESTER and wanted:
            chosen.append(wanted[extra % len(wanted)])   # extra section of a popular course
            extra += 1

        # Teachers who can teach this semester (the active semester only uses 'active' teachers)
        available = [t for t in teachers if t["dept"] == dept_code
                     and (t["status"] == "active" or not semester["is_active"])]
        load = {t["id"]: 0 for t in available}
        demo = next((t for t in available if t["is_demo"]), None)

        section_count: dict[int, int] = {}
        for index, course in enumerate(chosen):
            section_count[course["id"]] = section_count.get(course["id"], 0) + 1
            section = "ABCDEFG"[section_count[course["id"]] - 1]

            # The demo teacher always teaches the first two CSE offerings of the active semester
            if demo and semester["is_active"] and index < 2:
                teacher = demo
            else:
                teacher = rng.choice([t for t in available if load[t["id"]] < 3])
            load[teacher["id"]] += 1

            offerings.append({
                "course": course, "section": section, "teacher": teacher,
                "capacity": 40 if course["is_lab"] else rng.choice([30, 35, 40, 45, 50]),
                "popularity": rng.uniform(0.3, 1.0),
                "soft_limit": None,           # used to make some offerings nearly empty
                "status": "open" if semester["is_active"] else "closed",
                "students": [],               # filled by allocate_students()
                "dropped": set(),             # ids of students who dropped it (active semester only)
                "scheduled": True,
            })

    # Some offerings are nearly empty: at most 2-5 students may join them
    unpopular = rng.sample(offerings, 3)
    for offering in unpopular:
        offering["soft_limit"] = rng.randint(2, 5)
    if semester["is_active"]:
        # One active offering is cancelled (no students, no schedule),
        # and one has no room/time yet ("TBA"), which is useful for the outer-join queries.
        unpopular[0].update({"soft_limit": 0, "status": "cancelled", "scheduled": False})
        unpopular[1]["scheduled"] = False
    return offerings


def takes_classes(student: dict, semester: dict) -> bool:
    """New admissions never have classes yet; in the active semester only 'active' students study."""
    if student["is_new"]:
        return False
    return student["status"] == "active" or not semester["is_active"]


def is_eligible(student: dict, course: dict, prereqs: dict, passed: dict[int, set]) -> bool:
    """A student may take a course they have not passed yet, once ALL its prerequisites are passed."""
    done = passed[student["id"]]
    return course["id"] not in done and all(p in done for p in prereqs[course["id"]])


def allocate_students(semester: dict, offerings: list[dict], students: list[dict], prereqs: dict,
                      passed: dict[int, set]) -> None:
    """
    Put students into offerings. Each student wants 2-3 courses (about 2.75 on average).
    Mostly they take courses of their own department; level-1 courses of OTHER
    departments are allowed as electives, but are chosen less often.
    Students are processed in random order, so popular offerings fill up
    and late students must pick something else.
    """
    order = [s for s in students if takes_classes(s, semester)]
    rng.shuffle(order)

    for student in order:
        wanted_count = 2 if student["is_demo"] and semester["is_active"] else rng.choice([2, 3, 3, 3])
        picked_courses: set[int] = set()

        for _ in range(wanted_count):
            options = [
                o for o in offerings
                if (o["course"]["dept"] == student["dept"] or o["course"]["level"] == 1)
                and o["status"] != "cancelled"
                and o["course"]["id"] not in picked_courses
                and is_eligible(student, o["course"], prereqs, passed)
                and len(o["students"]) < o["capacity"]
                and (o["soft_limit"] is None or len(o["students"]) < o["soft_limit"])
            ]
            if not options:
                break
            # Electives from other departments get a quarter of the normal weight
            weights = [o["popularity"] * (1.0 if o["course"]["dept"] == student["dept"] else 0.25)
                       for o in options]
            offering = weighted_pick(options, weights)
            offering["students"].append(student)
            picked_courses.add(offering["course"]["id"])

            # In the active semester ~3% of students drop a course again (never the demo student)
            if semester["is_active"] and not student["is_demo"] and rng.random() < 0.03:
                offering["dropped"].add(student["id"])

    # Make the 3 busiest offerings exactly FULL (capacity = number of students still in it)
    def seats_taken(offering: dict) -> int:
        return len(offering["students"]) - len(offering["dropped"])

    busiest = sorted(offerings, key=seats_taken, reverse=True)[:3]
    for offering in busiest:
        if seats_taken(offering) >= 10:
            offering["capacity"] = seats_taken(offering)


def book_schedules(conn, offerings: list[dict], rooms: list[dict]) -> int:
    """
    Give every scheduled offering two weekly slots (same time, two days) without clashes.

    Python checks for clashes first (greedy search), and the triggers
    trg_no_room_conflict / trg_no_teacher_conflict are the final safety net.

    Returns:
        How many class_schedules rows were inserted.
    """
    room_busy: set[tuple] = set()      # (room_id, day, slot)
    teacher_busy: set[tuple] = set()   # (teacher_id, day, slot)
    inserted = 0

    for offering in offerings:
        offering["days"] = []
        if not offering["scheduled"]:
            continue
        need_type = ["lab"] if offering["course"]["is_lab"] else ["lecture", "seminar"]
        suitable = [r for r in rooms if r["type"] in need_type and r["capacity"] >= offering["capacity"]]

        choices = [(pair, slot, room) for pair in DAY_PAIRS for slot in range(len(TIME_SLOTS)) for room in suitable]
        rng.shuffle(choices)
        teacher_id = offering["teacher"]["id"]

        for (day_a, day_b), slot, room in choices:
            free = all((room["id"], d, slot) not in room_busy and (teacher_id, d, slot) not in teacher_busy
                       for d in (day_a, day_b))
            if not free:
                continue
            start_time, end_time = TIME_SLOTS[slot]
            for day in (day_a, day_b):
                conn.execute(
                    """INSERT INTO class_schedules (offering_id, room_id, day_of_week, start_time, end_time)
                       VALUES (?, ?, ?, ?, ?)""",
                    (offering["id"], room["id"], day, start_time, end_time),
                )
                room_busy.add((room["id"], day, slot))
                teacher_busy.add((teacher_id, day, slot))
                inserted += 1
            offering["days"] = [day_a, day_b]
            break
        else:
            raise RuntimeError(f"No free room/time found for offering {offering['id']}")
    return inserted


def seed_semester(conn, semester: dict, courses: list[dict], prereqs: dict, students: list[dict],
                  teachers: list[dict], rooms: list[dict], passed: dict[int, set], stats: dict) -> list[dict]:
    """
    Create all teaching data of ONE semester and update `passed` with the new passes.

    Returns:
        The list of enrollments created: {"id", "student", "status"}. Used for invoices.
    """
    offerings = plan_offerings(semester, courses, prereqs, students, passed, teachers)
    allocate_students(semester, offerings, students, prereqs, passed)

    # --- course_offerings ---
    for offering in offerings:
        offering["id"] = insert(
            conn,
            """INSERT INTO course_offerings (course_id, semester_id, teacher_id, section, capacity, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (offering["course"]["id"], semester["id"], offering["teacher"]["id"], offering["section"],
             offering["capacity"], offering["status"]),
        )
    stats["class_schedules"] += book_schedules(conn, offerings, rooms)

    new_passes: list[tuple[int, int]] = []
    enrollments_made: list[dict] = []
    results_rows, attendance_rows = [], []

    for offering in offerings:
        if offering["status"] == "cancelled":
            continue

        # --- assessments (4 per offering, weights add up to 100) ---
        assessments = []
        for title, a_type, max_marks, weight, due_after in ASSESSMENT_PLAN:
            due = semester["start"] + timedelta(days=due_after)
            assessment_id = insert(
                conn,
                """INSERT INTO assessments (offering_id, title, type, max_marks, weight_percent, due_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (offering["id"], title, a_type, max_marks, weight, due.isoformat()),
            )
            assessments.append({"id": assessment_id, "type": a_type, "max": max_marks,
                                "weight": weight, "due": due})

        # Class dates = the scheduled weekdays between the semester start and attendance_until
        class_dates = []
        day = semester["start"]
        while day < semester["attendance_until"]:
            if db_day_of_week(day) in offering["days"]:
                class_dates.append(day)
            day += timedelta(days=1)

        teacher_user = offering["teacher"]["user_id"]

        for student in offering["students"]:
            enrolled_at = random_time_on(random_day(semester["reg_start"], semester["start"]))
            # How well this student does in THIS course: their ability + some luck
            performance = student["ability"] + rng.gauss(0, 6)

            # Marks per assessment. Past semesters: all 4. Active: only those already due.
            marks = []
            for assessment in assessments:
                if assessment["due"] >= TODAY:
                    continue
                percent = min(100.0, max(0.0, rng.gauss(performance, 9)))
                obtained = round(percent / 100 * assessment["max"] * 2) / 2      # steps of 0.5
                marks.append((assessment, obtained))

            if semester["is_active"]:
                dropped = student["id"] in offering["dropped"]
                status = "dropped" if dropped else "enrolled"
                dropped_at = random_time_on(random_day(semester["start"], TODAY - timedelta(days=1))) if dropped else None
                total = grade_point = letter = None
            else:
                status, dropped_at = "completed", None
                # Same formula as calculate_final_marks(): SUM(obtained / max * weight)
                total = round(sum(obt / a["max"] * a["weight"] for a, obt in marks), 2)
                grade_point, letter = marks_to_gpa(total)

            enrollment_id = insert(
                conn,
                """INSERT INTO enrollments (student_id, offering_id, enrolled_at, status, total_marks,
                                            grade_point, letter_grade, dropped_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (student["id"], offering["id"], enrolled_at, status, total, grade_point, letter, dropped_at),
            )
            enrollments_made.append({"id": enrollment_id, "student": student, "status": status})
            if grade_point is not None and grade_point >= PASS_GRADE_POINT:
                new_passes.append((student["id"], offering["course"]["id"]))
            if status == "dropped":
                continue

            # --- assessment_results ---
            for assessment, obtained in marks:
                submitted = (random_time_on(assessment["due"] - timedelta(days=rng.randint(0, 3)))
                             if assessment["type"] in ("assignment", "project") else None)
                results_rows.append((assessment["id"], enrollment_id, obtained, submitted, teacher_user))

            # --- attendance ---
            for class_day in class_dates:
                roll = rng.random()
                remarks = None
                if roll < student["attend_rate"]:
                    status_today = "late" if rng.random() < 0.08 else "present"
                elif rng.random() < 0.15:
                    status_today, remarks = "excused", rng.choice(["Medical leave", "Family emergency",
                                                                   "University sports event"])
                else:
                    status_today = "absent"
                attendance_rows.append((enrollment_id, class_day.isoformat(), status_today, remarks, teacher_user))

    # executemany() = one prepared statement run for many rows: much faster than a Python loop of execute()
    conn.executemany(
        """INSERT INTO assessment_results (assessment_id, enrollment_id, marks_obtained, submitted_at, graded_by)
           VALUES (?, ?, ?, ?, ?)""",
        results_rows,
    )
    conn.executemany(
        "INSERT INTO attendance (enrollment_id, class_date, status, remarks, recorded_by) VALUES (?, ?, ?, ?, ?)",
        attendance_rows,
    )

    # Passes only count from the NEXT semester on
    for student_id, course_id in new_passes:
        passed[student_id].add(course_id)
    return enrollments_made


# =============================================================================
# Step 4: billing (invoices, items, payments)
# =============================================================================
def split_amount(total: int, parts: int) -> list[int]:
    """Split an amount (paisa) into `parts` installments in whole taka; the last one takes the remainder."""
    if parts == 1:
        return [total]
    amounts, remaining = [], total
    for index in range(parts - 1):
        share = remaining * rng.uniform(0.3, 0.6)
        amount = max(100, int(share // 100) * 100)     # whole taka
        amounts.append(amount)
        remaining -= amount
    amounts.append(remaining)
    return amounts


def seed_billing(conn, semesters: list[dict], enrollments_by_semester: dict, fees: dict,
                 accountants: list[int], stats: dict) -> None:
    """
    One invoice per student per semester in which they enrolled, with 3 items each.
    Payment behaviour:
        past semesters  : 88% fully paid, 7% partial, 5% unpaid
        active semester : 55% fully paid, 25% partial, 20% unpaid
    """
    ref_number = 1
    payment_rows = []

    for semester in semesters:
        sem_fees = fees[semester["id"]]
        issued = semester["reg_start"]
        # Fees are due ~11 weeks into the semester. For the active semester that
        # is still ~2 weeks away, so its unpaid invoices are 'unpaid'/'partial', not overdue.
        due = semester["start"] + timedelta(days=INVOICE_DUE_DAYS)

        # distinct students of this semester, in a stable order
        seen, semester_students = set(), []
        for enrollment in enrollments_by_semester[semester["id"]]:
            if enrollment["student"]["id"] not in seen:
                seen.add(enrollment["student"]["id"])
                semester_students.append(enrollment["student"])

        for student in semester_students:
            # Department-specific tuition overrides the global (None) row
            tuition_id, tuition = sem_fees["tuition"].get(student["dept"], sem_fees["tuition"][None])
            exam_id, exam = sem_fees["exam"][None]
            library_id, library = sem_fees["library"][None]
            items = [(tuition_id, "Tuition fee", tuition), (exam_id, "Examination fee", exam),
                     (library_id, "Library fee", library)]
            total = sum(amount for _, _, amount in items)

            invoice_id = insert(
                conn,
                """INSERT INTO invoices (student_id, semester_id, invoice_no, total_amount, issued_at, due_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (student["id"], semester["id"], f"INV-{semester['code']}-{student['code']}", total,
                 ts(issued, 9), due.isoformat()),
            )
            conn.executemany(
                "INSERT INTO invoice_items (invoice_id, fee_structure_id, description, amount) VALUES (?, ?, ?, ?)",
                [(invoice_id, fee_id, description, amount) for fee_id, description, amount in items],
            )
            stats["invoice_items"] += len(items)

            # How much of this invoice gets paid?
            if student["is_demo"] and semester["is_active"]:
                plan = "partial"
            elif semester["is_active"]:
                plan = weighted_pick(["paid", "partial", "unpaid"], [55, 25, 20])
            else:
                plan = weighted_pick(["paid", "partial", "unpaid"], [88, 7, 5])

            if plan == "paid":
                installments = split_amount(total, weighted_pick([1, 2, 3], [35, 45, 20]))
            elif plan == "partial":
                installments = [int(total * rng.uniform(0.3, 0.7)) // 100 * 100]
            else:
                installments = []

            last_day = min(due + timedelta(days=40), TODAY - timedelta(days=1))
            pay_days = sorted(random_day(issued, last_day) for _ in installments)
            for amount, pay_day in zip(installments, pay_days):
                method = weighted_pick(PAYMENT_METHODS, PAYMENT_METHOD_WEIGHTS)
                reference = None if method == "cash" else f"{method[:2].upper()}{1000000 + ref_number}"
                ref_number += 1
                payment_rows.append((invoice_id, amount, method, reference, random_time_on(pay_day),
                                     rng.choice(accountants)))

    # The trigger trg_payment_update_invoice fires for every row and updates the invoice
    conn.executemany(
        """INSERT INTO payments (invoice_id, amount, method, transaction_ref, paid_at, received_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        payment_rows,
    )

    # Past the due date and still not fully paid -> overdue
    conn.execute(
        "UPDATE invoices SET status = 'overdue' WHERE paid_amount < total_amount AND due_date < ?",
        (TODAY.isoformat(),),
    )


# =============================================================================
# Step 5: announcements
# =============================================================================
def seed_announcements(conn, admin_id: int, dept_ids: dict[str, int], semesters: list[dict]) -> None:
    """A dozen announcements with different audiences, some already expired."""
    active = semesters[-1]
    items = [
        (f"Welcome to {active['code']}", "Classes have started. Check your routine and course materials.", None, None),
        ("Add/Drop deadline", "The add/drop window closes in two weeks. Late changes need approval.", "student", None),
        ("Midterm grade submission", "Please submit midterm marks through the gradebook by Friday.", "teacher", None),
        ("Fee payment reminder", "Invoices are overdue for many students. Please follow up.", "accountant", None),
        ("Scholarship applications open", fake.paragraph(nb_sentences=3), "student", None),
        ("System maintenance", "UCMS will be offline on Saturday from 01:00 to 03:00.", None, None),
        ("CSE project showcase", fake.paragraph(nb_sentences=2), None, dept_ids["CSE"]),
        ("EEE lab safety training", "All EEE students must attend the lab safety session.", "student", dept_ids["EEE"]),
        ("BBA industry talk", fake.paragraph(nb_sentences=2), None, dept_ids["BBA"]),
        ("New audit log review policy", "Admins must review audit logs every week.", "admin", None),
        ("Library hours extended", "The library is open until 22:00 during exams.", None, None),
        ("Old notice: previous semester results", "Results of the previous semester are published.", "student", None),
    ]
    for index, (title, body, role, dept_id) in enumerate(items):
        published = TODAY - timedelta(days=rng.randint(1, 55))
        # The last item is expired; a few others expire in the future; the rest never expire
        if index == len(items) - 1:
            published = TODAY - timedelta(days=90)
            expires = ts(TODAY - timedelta(days=30), 23, 59)
        else:
            expires = ts(TODAY + timedelta(days=rng.randint(10, 60)), 23, 59) if index % 3 == 0 else None
        conn.execute(
            """INSERT INTO announcements (title, body, posted_by, target_role, target_department_id,
                                          published_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, body, admin_id, role, dept_id, random_time_on(published), expires),
        )


# =============================================================================
# Main
# =============================================================================
def seed_database(db_path: Path | str | None = None) -> None:
    """Insert all demo data into an EMPTY database (inside one transaction)."""
    assert sum(weight for _, _, _, weight, _ in ASSESSMENT_PLAN) == 100, "assessment weights must sum to 100"

    # bcrypt is slow on purpose (that makes password guessing slow), so we hash
    # the demo password ONCE and reuse it for every seeded account. (DECISIONS.md)
    password_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(DEMO_PASSWORD)

    conn = get_connection(db_path)
    stats = {"class_schedules": 0, "invoice_items": 0}
    try:
        with transaction(conn, actor_id=None):
            staff = seed_staff_users(conn, password_hash)
            admin_id = staff["admin"][0]
            # From now on the audit triggers record the admin as the one making changes
            set_actor(conn, admin_id)

            dept_ids = seed_departments(conn)
            teachers = seed_teachers(conn, dept_ids, password_hash)
            semesters = seed_semesters(conn)
            students = seed_students(conn, dept_ids, password_hash, semesters[0]["start"], semesters[-1]["start"])
            rooms = seed_rooms(conn)
            courses, prereqs = seed_courses(conn, dept_ids)
            fees = seed_fee_structures(conn, semesters, dept_ids)

            passed: dict[int, set] = {s["id"]: set() for s in students}
            enrollments_by_semester = {}
            for semester in semesters:            # oldest first, so prerequisites build up
                enrollments_by_semester[semester["id"]] = seed_semester(
                    conn, semester, courses, prereqs, students, teachers, rooms, passed, stats)

            seed_billing(conn, semesters, enrollments_by_semester, fees, staff["accountant"], stats)
            seed_announcements(conn, admin_id, dept_ids, semesters)

        refresh_department_performance(conn, actor_id=admin_id)
    finally:
        conn.close()


def print_summary(db_path: Path | str | None = None) -> None:
    """Print a row count per table, plus a few numbers that prove the realism rules."""
    conn = get_connection(db_path)
    try:
        print("\nRow counts")
        print("-" * 42)
        total = 0
        for name in list_tables(conn):
            if name.startswith("sqlite_") or name == "_audit_actor":
                continue
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            total += count
            print(f"  {name:<28} {count:>9,}")
        print("-" * 42)
        print(f"  {'TOTAL':<28} {total:>9,}")

        # --- realism checks ---
        low = fetch_value(conn, """
            SELECT ROUND(100.0 * SUM(pct < 75) / COUNT(*), 1) FROM (
                SELECT student_id, 100.0 * SUM(present_count) / SUM(total_classes) AS pct
                FROM v_attendance_percentage WHERE total_classes > 0 GROUP BY student_id)""")
        unpaid = fetch_value(conn, "SELECT ROUND(100.0 * SUM(status <> 'paid') / COUNT(*), 1) FROM invoices")
        full = fetch_value(conn, """SELECT COUNT(*) FROM v_offering_summary
                                    WHERE total_students = capacity AND status <> 'cancelled'""")
        near_empty = fetch_value(conn, "SELECT COUNT(*) FROM v_offering_summary WHERE total_students BETWEEN 1 AND 5")
        weights_ok = fetch_value(conn, """SELECT COUNT(*) FROM (SELECT offering_id, SUM(weight_percent) w
                                          FROM assessments GROUP BY offering_id) WHERE w <> 100""")
        grades = conn.execute("""SELECT letter_grade, COUNT(*) FROM enrollments WHERE status = 'completed'
                                 GROUP BY letter_grade ORDER BY MIN(grade_point) DESC""").fetchall()

        print("\nRealism checks")
        print(f"  students with attendance < 75%      : {low}%   (target ~15%)")
        print(f"  invoices unpaid / partial / overdue : {unpaid}%   (target ~20%)")
        print(f"  full offerings                      : {full}")
        print(f"  near-empty offerings (1-5 students) : {near_empty}")
        print(f"  offerings whose weights != 100      : {weights_ok}   (must be 0)")
        print("  grade distribution (completed)      : " + "  ".join(f"{g}:{n}" for g, n in grades))
        print(f"\nDemo logins (password {DEMO_PASSWORD}): admin@ucms.edu, teacher@ucms.edu, "
              "student@ucms.edu, accountant@ucms.edu")
    finally:
        conn.close()


def main() -> int:
    """Command-line entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(description="Seed the UCMS database with demo data.")
    parser.add_argument("--reset", action="store_true", help="delete the database and rebuild it first")
    args = parser.parse_args()
    db_path = config.DB_PATH

    if args.reset:
        try:
            delete_database_files(db_path)
        except PermissionError:
            print("ERROR: the database file is in use. Stop the server (run.py) and try again.")
            return 1

    # Create the schema if the database does not exist yet
    conn = get_connection(db_path)
    has_tables = bool(list_tables(conn))
    has_data = has_tables and fetch_value(conn, "SELECT COUNT(*) FROM users") > 0
    conn.close()

    if has_data:
        print("ERROR: the database already has data. Use `python scripts/seed.py --reset` to start over.")
        return 1
    if not has_tables:
        init_database(db_path, verbose=False)

    started = time.perf_counter()
    print("Seeding ...")
    seed_database(db_path)
    print(f"Done in {time.perf_counter() - started:.1f} s")
    print_summary(db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
