import io
import json
import zipfile

from tests.test_grading import REPORT, course, project  # noqa: F401  (fixtures)


def test_staff_and_student_reports(client, users, project, analyzer):  # noqa: F811
    analyzer.routes["/internal/reports/student"] = (200, {"ok": True})
    faculty = client.get(f"/api/v1/reports/student/{project}/pdf", headers=users["faculty"].headers)
    assert faculty.status_code == 200 and faculty.headers["content-type"] == "application/pdf"
    staff_payload = json.loads(analyzer.route_calls[-1].content)
    assert staff_payload["audience"] == "staff"
    assert staff_payload["authenticity"]["authenticity_score"] == 92.4
    assert staff_payload["grade"]["suggested_total"] == 81.5
    assert staff_payload["security"]["vulnerabilities"][0]["type"] == "SQL Injection"
    assert staff_payload["code"]["details"]["stack"]["technologies"][0]["name"] == "Flask"

    client.get(f"/api/v1/reports/student/{project}/pdf", headers=users["student"].headers)
    student_payload = json.loads(analyzer.route_calls[-1].content)
    assert student_payload["audience"] == "student"
    assert student_payload["authenticity"] is None
    assert student_payload["grade"]["suggested_total"] is None
    other = client.get(
        f"/api/v1/reports/student/{project}/pdf", headers=users["other_faculty"].headers
    )
    assert other.status_code == 404


def test_course_zip(client, users, course, project, analyzer):  # noqa: F811
    analyzer.routes["/internal/reports/student"] = (200, {"ok": True})
    response = client.get(f"/api/v1/reports/course/{course['id']}/pdf.zip",
                          headers=users["faculty"].headers)  # fmt: skip
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert len(names) == 1 and names[0].endswith(".pdf")
    assert client.get(f"/api/v1/reports/course/{course['id']}/pdf.zip",
                      headers=users["student"].headers).status_code == 403  # fmt: skip


def test_generator_down(client, users, project, analyzer):  # noqa: F811
    analyzer.routes["/internal/reports/student"] = (503, {})
    response = client.get(
        f"/api/v1/reports/student/{project}/pdf", headers=users["faculty"].headers
    )
    assert response.status_code == 503
