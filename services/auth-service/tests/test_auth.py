STUDENT = {
    "username": "khalid",
    "email": "khalid@example.com",
    "password": "s3cure-pass",
    "full_name": "خالد أحمد",
    "student_id": "2022001",
}


def register(client, **overrides):
    return client.post("/api/v1/auth/register", json={**STUDENT, **overrides})


def login(client, username="khalid", password="s3cure-pass"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def admin_headers(client):
    return bearer(login(client, "admin", "admin-password-1").json()["access_token"])


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_register_creates_student_and_hides_password(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "student"
    assert body["full_name"] == "خالد أحمد"
    assert "password" not in body and "password_hash" not in body


def test_register_cannot_choose_role(client):
    assert register(client, role="admin").json()["role"] == "student"


def test_register_duplicate_rejected(client):
    register(client)
    assert register(client).status_code == 409
    assert register(client, username="other").status_code == 409  # same email


def test_register_validation(client):
    assert register(client, password="short").status_code == 422
    assert register(client, email="not-an-email").status_code == 422
    assert register(client, username="bad name!").status_code == 422
    assert register(client, password="ك" * 40).status_code == 422  # 80 bytes


def test_login_with_username_or_email(client):
    register(client)
    assert login(client).status_code == 200
    assert login(client, username="KHALID@example.com").status_code == 200


def test_login_wrong_credentials_are_indistinguishable(client):
    register(client)
    wrong_password = login(client, password="nope-nope")
    unknown_user = login(client, username="ghost")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_me_requires_access_token(client):
    register(client)
    tokens = login(client).json()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer("garbage")).status_code == 401
    # A refresh token must not work as an access token.
    assert client.get("/api/v1/auth/me", headers=bearer(tokens["refresh_token"])).status_code == 401
    me = client.get("/api/v1/auth/me", headers=bearer(tokens["access_token"]))
    assert me.status_code == 200 and me.json()["username"] == "khalid"


def test_refresh_rotates_token(client):
    register(client)
    tokens = login(client).json()
    body = {"refresh_token": tokens["refresh_token"]}
    refreshed = client.post("/api/v1/auth/refresh-token", json=body)
    assert refreshed.status_code == 200
    assert client.post("/api/v1/auth/refresh-token", json=body).status_code == 401  # reuse
    access_as_refresh = {"refresh_token": tokens["access_token"]}
    assert client.post("/api/v1/auth/refresh-token", json=access_as_refresh).status_code == 401


def test_logout_revokes_refresh_token(client):
    register(client)
    body = {"refresh_token": login(client).json()["refresh_token"]}
    assert client.post("/api/v1/auth/logout", json=body).status_code == 204
    assert client.post("/api/v1/auth/refresh-token", json=body).status_code == 401


def test_bootstrap_admin_and_rbac(client):
    register(client)
    student = bearer(login(client).json()["access_token"])
    admin = admin_headers(client)

    assert client.get("/api/v1/users", headers=student).status_code == 403
    assert client.get("/api/v1/users").status_code == 401
    users = client.get("/api/v1/users", headers=admin)
    assert users.status_code == 200 and len(users.json()) == 2

    faculty = {
        "username": "dr.ali",
        "email": "ali@example.com",
        "password": "faculty-pass",
        "full_name": "د. علي",
        "role": "faculty",
    }
    assert client.post("/api/v1/users", json=faculty, headers=student).status_code == 403
    created = client.post("/api/v1/users", json=faculty, headers=admin)
    assert created.status_code == 201 and created.json()["role"] == "faculty"
    listed = client.get("/api/v1/users", params={"role": "faculty"}, headers=admin).json()
    assert [user["username"] for user in listed] == ["dr.ali"]


def test_user_can_read_only_own_profile(client):
    own_id = register(client).json()["id"]
    other_id = register(client, username="sara", email="sara@example.com").json()["id"]
    student = bearer(login(client).json()["access_token"])
    assert client.get(f"/api/v1/users/{own_id}", headers=student).status_code == 200
    assert client.get(f"/api/v1/users/{other_id}", headers=student).status_code == 403
    assert client.get(f"/api/v1/users/{other_id}", headers=admin_headers(client)).status_code == 200
