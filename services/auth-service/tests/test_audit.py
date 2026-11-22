from tests.test_auth import admin_headers, bearer, login, register


def test_logins_and_failures_are_audited(client):
    bad = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-pass-1"})
    assert bad.status_code == 401
    admin = admin_headers(client)
    assert client.get("/api/v1/audit").status_code == 401
    entries = client.get("/api/v1/audit", headers=admin).json()
    logins = [e for e in entries if e["path"] == "/api/v1/auth/login"]
    assert sorted(e["status_code"] for e in logins) == [200, 401]
    assert all(e["ip"] for e in logins)
    assert all("password" not in str(e) for e in entries)


def test_students_cannot_read_the_audit_log(client):
    assert register(client).status_code == 201
    token = login(client).json()["access_token"]
    assert client.get("/api/v1/audit", headers=bearer(token)).status_code == 403
