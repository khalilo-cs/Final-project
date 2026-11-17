import csv
import json

import httpx

from tools.evaluation.evaluate import Api, Row, build, join, main, read_committee, render


def rows():
    return [
        Row("p1", "2022001", "نظام مكتبة", 88.0, 100.0, None),
        Row("p2", "2022002", "متجر إلكتروني", 71.0, 90.0, None),
        Row("p3", "2022003", "عيادة", 60.0, 100.0, 75.0),
        Row("p4", "2022004", "حجوزات", None, 40.0, None),
    ]


def write_csv(path, entries):
    with open(path, "w", encoding="utf-8-sig", newline="") as sink:
        writer = csv.DictWriter(
            sink, fieldnames=["student_number", "project_id", "faculty_grade", "authored"]
        )
        writer.writeheader()
        writer.writerows(entries)


def test_join_by_number_or_id_with_arabic_digits(tmp_path):
    path = tmp_path / "committee.csv"
    write_csv(path, [
        {"student_number": "2022001", "faculty_grade": "٩٠", "authored": "نعم"},
        {"project_id": "p2", "faculty_grade": "68.5", "authored": "no"},
        {"student_number": "2022003", "faculty_grade": "200"},
        {"student_number": "9999", "faculty_grade": "50"},
    ])  # fmt: skip
    joined, problems = join(rows(), read_committee(path))
    assert [r.faculty for r in joined] == [90.0, 68.5, None, None]
    assert [r.authored for r in joined[:2]] == [True, False]
    assert len(problems) == 2 and "200" in problems[0] and "9999" in problems[1]


def test_report_flags_in_system_grades_and_renders(tmp_path):
    report = build("c1", rows(), None)
    assert report.source == "in_system" and report.agreement is None  # only p3 has both
    page = render(report)
    assert "بعد رؤية الدرجة" in page and "مشروعان على الأقل" in page

    committee = [
        {"project_id": p, "faculty_grade": g} for p, g in [("p1", "85"), ("p2", "74"), ("p3", "63")]
    ]
    report = build("c1", rows(), committee)
    assert report.source == "blind" and report.agreement.n == 3
    assert any("حجوزات" in p for p in report.skipped)  # no suggested grade
    page = render(report)
    assert "<svg" in page and "بعد رؤية الدرجة" not in page and "نظام مكتبة" in page


def test_fingerprint_pilot():
    data = rows()
    data[0].fingerprint, data[1].fingerprint, data[2].fingerprint = 100.0, 20.0, 80.0
    committee = [
        {"project_id": "p1", "faculty_grade": "85", "authored": "yes"},
        {"project_id": "p2", "faculty_grade": "74", "authored": "no"},
        {"project_id": "p3", "faculty_grade": "63", "authored": "yes"},
    ]
    report = build("c1", data, committee)
    assert report.fingerprint == {"authors": 2, "others": 1, "mean_authors": 90.0,
                                  "mean_others": 20.0, "auc": 1.0}  # fmt: skip
    assert "AUC = 1.00" in render(report)


def test_command_line_against_a_fake_server(tmp_path, monkeypatch):
    def server(request: httpx.Request):
        if request.url.path == "/svc/auth/api/v1/auth/login":
            assert json.loads(request.content)["username"] == "dr.ali"
            return httpx.Response(200, json={"access_token": "t"})
        assert request.headers["authorization"] == "Bearer t"
        if request.url.path == "/svc/projects/api/v1/grades/course/c1":
            return httpx.Response(200, json={"projects": [
                {"project_id": "p1", "student_number": "1", "title": "أ", "suggested_total": 80,
                 "coverage": 100, "final_total": 82},
                {"project_id": "p2", "student_number": "2", "title": "ب", "suggested_total": 60,
                 "coverage": 100, "final_total": 55},
                {"project_id": "p3", "student_number": "3", "title": "ج", "suggested_total": 92,
                 "coverage": 100, "final_total": 95},
            ]})  # fmt: skip
        return httpx.Response(404)

    original = Api.__init__
    monkeypatch.setattr(
        Api, "__init__", lambda self, base: original(self, base, httpx.MockTransport(server))
    )
    monkeypatch.setattr("getpass.getpass", lambda prompt: "secret")
    out, raw = tmp_path / "r.html", tmp_path / "r.json"
    assert main(["--course", "c1", "--user", "dr.ali", "--out", str(out), "--json", str(raw)]) == 0
    assert "نتائج تقييم" in out.read_text(encoding="utf-8")
    assert json.loads(raw.read_text(encoding="utf-8"))["agreement"]["n"] == 3
