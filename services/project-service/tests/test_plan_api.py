from tests.test_projects import course, submit  # noqa: F401 - fixture


def test_plan_endpoints_exist_and_respect_roles(client, users, course):  # noqa: F811
    pid = submit(client, users["student"], course["id"]).json()["id"]
    staff, student, admin = (
        users["faculty"].headers,
        users["student"].headers,
        users["admin"].headers,
    )

    assert client.post(f"/api/v1/analysis/security/{pid}", headers=staff).status_code == 202
    assert client.post(f"/api/v1/fraud/analyze/{pid}", headers=student).status_code == 403
    assert client.post(f"/api/v1/fraud/analyze/{pid}", headers=staff).status_code == 202

    similar = client.get(f"/api/v1/fraud/{pid}/similar-projects", headers=staff)
    assert similar.status_code == 200 and "similar_projects" in similar.json()
    assert client.get(f"/api/v1/fraud/{pid}/similar-projects", headers=student).status_code == 403

    assert client.get(f"/api/v1/sandbox/{pid}/status", headers=student).json()["status"] in (
        "running", "unavailable", "done",
    )  # fmt: skip
    assert (
        client.get(f"/api/v1/sandbox/{pid}/screenshots", headers=staff).json()["screenshots"] == []
    )

    assert client.get(f"/api/v1/reports/course/{course['id']}", headers=staff).status_code == 200
    assert client.get(f"/api/v1/reports/course/{course['id']}", headers=student).status_code == 403
    assert client.get("/api/v1/reports/analytics/department", headers=staff).status_code == 200

    assert client.get("/api/v1/dashboard/admin/stats", headers=staff).status_code == 403
    stats = client.get("/api/v1/dashboard/admin/stats", headers=admin).json()
    assert stats["projects"] == 1 and stats["analysis_queue"].get("done", 0) >= 1
    assert stats["audited_actions_24h"] >= 3


def test_student_report_json_hides_staff_only_parts(client, users, course):  # noqa: F811
    pid = submit(client, users["student"], course["id"]).json()["id"]
    mine = client.get(f"/api/v1/reports/student/{pid}", headers=users["student"].headers)
    staff = client.get(f"/api/v1/reports/student/{pid}", headers=users["faculty"].headers)
    assert mine.status_code == 200 and staff.status_code == 200
    assert mine.json() != staff.json()
    assert client.get(f"/api/v1/reports/student/{pid}",
                      headers=users["other_faculty"].headers).status_code == 404  # fmt: skip
