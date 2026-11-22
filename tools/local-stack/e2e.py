"""End-to-end test of the whole running system, through the real web interface.

Start the stack first (tools/local-stack/run.sh), then:
    python tools/local-stack/e2e.py [--base http://localhost:8080] [--shots DIR]

What it does, like real people would:
  admin    creates a faculty account (API)
  faculty  creates a course and enrolls the student (API)
  student  signs in, submits a project (code + SQL + report) in the browser,
           waits for the analysis, reads the results, takes the AI viva
  faculty  sees the alerts, opens the project, approves a grade
  admin    reads the audit log
and checks every step on the real services (no mocks). Exit code 0 = all passed.
"""

import argparse
import io
import sys
import time
import uuid
import zipfile
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ADMIN = ("admin", "admin-password-1")

APP_PY = """from flask import Flask, request, render_template_string
import sqlite3

app = Flask(__name__)


class User:
    def __init__(self, name):
        self.name = name


class OrderService:
    def __init__(self, db):
        self.db = db

    def orders_of(self, users):
        totals = {}
        for user in users:
            cur = self.db.cursor()
            cur.execute("SELECT total FROM orders WHERE user_id = ?", (user.id,))
            totals[user.name] = cur.fetchall()
        return totals


@app.route("/search")
def search():
    name = request.args.get("name")
    db = sqlite3.connect("shop.db")
    rows = db.execute("SELECT * FROM users WHERE name = '" + name + "'").fetchall()
    return render_template_string("<p>{{ rows }}</p>", rows=rows)


@app.route("/transfer", methods=["POST"])
def transfer():
    amount = int(request.form["amount"])
    return str(amount)


def calculate_discount(total, is_member):
    if total > 100 and is_member:
        return total * 0.1
    if total > 100:
        return total * 0.05
    return 0
"""

SCHEMA = """
CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100), password VARCHAR(50));
CREATE TABLE orders (id INT PRIMARY KEY, user_id INT, total FLOAT);
"""


def make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("shop/app.py", APP_PY)
        bundle.writestr("shop/requirements.txt", "flask\n")
    return buffer.getvalue()


def make_report() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("Online shop", 0)
    doc.add_paragraph(
        "The system is written in Python with Flask and uses SQLite. The users table "
        "stores accounts and the orders table stores purchases. We also keep a table "
        "'payments' for invoices."
    )
    doc.add_heading("Class Diagram", 1)
    doc.add_paragraph("The class User is used by OrderService and by PaymentGateway.")
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


class Check:
    def __init__(self):
        self.passed: list[str] = []

    def __call__(self, label: str, condition: bool, detail: str = "") -> None:
        if not condition:
            print(f"  ✗ {label} {detail}")
            raise SystemExit(1)
        self.passed.append(label)
        print(f"  ✓ {label}")


def api(base: str):
    return httpx.Client(base_url=base, timeout=60)


def login_token(http: httpx.Client, username: str, password: str) -> str:
    response = http.post(
        "/svc/auth/api/v1/auth/login", json={"username": username, "password": password}
    )
    response.raise_for_status()
    return response.json()["access_token"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--shots", default=None, help="folder for screenshots")
    args = parser.parse_args()
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    check = Check()
    run = uuid.uuid4().hex[:6]
    http = api(args.base)
    work = Path(__import__("tempfile").mkdtemp(prefix="mihakk-e2e-"))
    (work / "shop.zip").write_bytes(make_zip())
    (work / "schema.sql").write_text(SCHEMA)
    (work / "report.docx").write_bytes(make_report())

    print("1. accounts and course (API)")
    admin = {"Authorization": f"Bearer {login_token(http, *ADMIN)}"}
    faculty_name, student_name = f"dr{run}", f"st{run}"
    created = http.post(
        "/svc/auth/api/v1/users",
        headers=admin,
        json={
            "username": faculty_name,
            "email": f"{faculty_name}@su.edu.ye",
            "password": "faculty-pass-1",
            "full_name": "د. هدى",
            "role": "faculty",
        },
    )
    check("admin creates a faculty account", created.status_code == 201, created.text)
    registered = http.post(
        "/svc/auth/api/v1/auth/register",
        json={
            "username": student_name,
            "email": f"{student_name}@su.edu.ye",
            "password": "student-pass-1",
            "full_name": "علي صالح",
            "student_id": "2022" + run[:3],
        },
    )
    check("student registers", registered.status_code == 201, registered.text)
    faculty = {"Authorization": f"Bearer {login_token(http, faculty_name, 'faculty-pass-1')}"}
    course = http.post(
        "/svc/projects/api/v1/courses",
        headers=faculty,
        json={
            "name": "مشروع تخرج",
            "code": f"CS{run[:3]}",
            "semester": "Fall",
            "year": 2026,
            "level": "year4",
            "kind": "graduation",
        },
    ).json()
    enrolled = http.post(
        f"/svc/projects/api/v1/courses/{course['id']}/students",
        headers=faculty,
        json={"student_ids": [registered.json()["id"]]},
    )
    check(
        "faculty creates a course and enrolls the student",
        enrolled.status_code == 200,
        enrolled.text,
    )

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("dialog", lambda dialog: dialog.accept())

        def shot(name: str) -> None:
            if shots:
                page.screenshot(path=str(shots / f"{name}.png"), full_page=True)

        def sign_in(username: str, password: str) -> None:
            page.goto(args.base + "/login")
            page.get_by_placeholder("اسم المستخدم أو البريد").fill(username)
            page.get_by_placeholder("كلمة المرور").fill(password)
            page.get_by_role("button", name="دخول", exact=True).click()
            page.wait_for_url(lambda url: "/login" not in url, timeout=15_000)

        print("2. student submits in the browser")
        sign_in(student_name, "student-pass-1")
        expect(page.get_by_text("تسليم مشروع جديد")).to_be_visible()
        page.get_by_placeholder("عنوان المشروع").fill("متجر إلكتروني")
        page.locator('input[name="code"]').set_input_files(str(work / "shop.zip"))
        page.locator('input[name="report"]').set_input_files(str(work / "report.docx"))
        page.locator('input[name="database"]').set_input_files(str(work / "schema.sql"))
        page.locator('select[name="db_dialect"]').select_option("sqlite")
        page.get_by_role("button", name="تسليم وتحليل").click()
        project_link = page.get_by_role("link", name="متجر إلكتروني").first
        project_link.wait_for(timeout=60_000)
        check("the submission appears in the student's list", project_link.is_visible())
        project_link.click()
        page.wait_for_url("**/projects/**")
        project_id = page.url.rstrip("/").split("/")[-1]

        print("3. analysis on the real services")
        student = {"Authorization": f"Bearer {login_token(http, student_name, 'student-pass-1')}"}
        status = {}
        for _ in range(120):
            status = http.get(
                f"/svc/projects/api/v1/projects/{project_id}/status", headers=student
            ).json()
            if status["status"] != "analyzing":
                break
            time.sleep(1)
        check("analysis finished", status.get("status") == "analyzed", str(status))
        security = http.get(
            f"/svc/projects/api/v1/analysis/security/{project_id}/results", headers=student
        ).json()
        kinds = {v["type"] for v in security["vulnerabilities"]}
        check("SQL injection found", "SQL Injection" in kinds, str(kinds))
        check("CSRF found", "CSRF" in kinds, str(kinds))
        code = http.get(
            f"/svc/projects/api/v1/analysis/code/{project_id}/results", headers=student
        ).json()
        smells = {s["type"] for s in code["code_smells"]}
        check("N+1 query found", "n_plus_one_query" in smells, str(smells))
        database = http.get(
            f"/svc/projects/api/v1/analysis/database/{project_id}/results", headers=student
        ).json()
        check(
            "database analyzed (missing foreign key)",
            bool(database["missing_foreign_keys"]),
            str(database)[:300],
        )
        report = http.get(
            f"/svc/projects/api/v1/analysis/report/{project_id}/results", headers=student
        ).json()
        issues = {i["type"] for i in report.get("inconsistencies", [])}
        check(
            "report: table not in schema + UML class not in code",
            {"table_not_in_schema", "uml_class_not_found"} <= issues,
            str(issues),
        )
        page.reload()
        expect(page.get_by_text("نتائج التحليل")).to_be_visible(timeout=15_000)
        shot("1-student-results")

        print("4. AI viva in the browser")
        page.get_by_role("button", name="ابدأ المناقشة الذكية").click()
        page.wait_for_url("**/viva/**", timeout=30_000)
        for _ in range(3):
            box = page.locator("textarea")
            box.wait_for(timeout=15_000)
            box.fill(
                "الدالة orders_of في OrderService تستعلم من جدول orders لكل مستخدم، "
                "والأفضل استعلام واحد مع IN لتجنب N+1، واستخدام معاملات بدل دمج النص."
            )
            page.get_by_role("button", name="إرسال الإجابة").click()
            page.wait_for_timeout(800)
        shot("2-viva")
        page.get_by_role("button", name="إنهاء المناقشة").click()
        expect(page.get_by_text("درجة المناقشة").first).to_be_visible(timeout=20_000)
        check("viva finished with a score", True)

        print("5. faculty reviews and grades")
        page.evaluate("sessionStorage.clear()")
        sign_in(faculty_name, "faculty-pass-1")
        alerts = http.get("/svc/projects/api/v1/dashboard/faculty/alerts", headers=faculty).json()
        check(
            "faculty gets an alert for the project",
            any(a["project_id"] == project_id for a in alerts),
            str(alerts)[:300],
        )
        page.goto(f"{args.base}/projects/{project_id}")
        total = page.locator('input[type="number"]').last
        total.wait_for(timeout=20_000)
        total.fill("72")
        page.get_by_role("button", name="اعتماد الدرجة").click()
        page.wait_for_timeout(1500)
        grade = http.get(f"/svc/projects/api/v1/grades/{project_id}", headers=faculty).json()
        check("grade approved", grade.get("final_total") == 72, str(grade)[:300])
        shot("3-faculty-project")

        print("6. English interface")
        page.get_by_role("button", name="English").click()
        page.wait_for_load_state()
        expect(page.get_by_text("Final grade").first).to_be_visible(timeout=10_000)
        check(
            "interface switches to English (ltr)",
            page.evaluate("document.documentElement.dir") == "ltr",
        )
        shot("4-english")
        page.evaluate("localStorage.removeItem('mihakk.lang')")
        browser.close()

    print("7. audit log")
    entries = http.get(f"/svc/projects/api/v1/audit?target_id={project_id}", headers=admin).json()
    check(
        "audit log records the grade approval",
        any(e["method"] == "PUT" and "/grades/" in e["path"] for e in entries),
        str(entries)[:300],
    )
    check("audit log records the real client address", all(e["ip"] for e in entries))

    print(f"\nall {len(check.passed)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
