from tests.test_projects import course, submit  # noqa: F401 - fixture


def test_mutations_are_audited_and_only_admins_read_them(client, users, course):  # noqa: F811
    response = submit(client, users["student"], course["id"])
    project_id = response.json()["id"]
    client.get(f"/api/v1/projects/{project_id}/code", headers=users["student"].headers)
    client.get("/api/v1/courses", headers=users["faculty"].headers)  # plain reads: not logged

    assert client.get("/api/v1/audit", headers=users["faculty"].headers).status_code == 403
    assert client.get("/api/v1/audit").status_code == 401
    entries = client.get("/api/v1/audit", headers=users["admin"].headers).json()
    by_path = {(e["method"], e["path"]): e for e in entries}
    created = by_path[("POST", "/api/v1/projects")]
    assert created["actor_id"] == str(users["student"].id)
    assert created["actor_role"] == "student" and created["status_code"] == 201
    download = by_path[("GET", f"/api/v1/projects/{project_id}/code")]
    assert download["target_id"] == project_id
    assert ("GET", "/api/v1/courses") not in by_path
    # Filter by the project.
    only = client.get(
        f"/api/v1/audit?target_id={project_id}", headers=users["admin"].headers
    ).json()
    assert {e["target_id"] for e in only} == {project_id}
