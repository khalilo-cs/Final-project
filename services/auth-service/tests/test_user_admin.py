from tests.test_auth import admin_headers, bearer, login, register


def test_admin_changes_role_and_deletes(client):
    student = register(client).json()
    admin = admin_headers(client)
    changed = client.put(f"/api/v1/users/{student['id']}", json={"role": "faculty"}, headers=admin)
    assert changed.status_code == 200 and changed.json()["role"] == "faculty"
    refresh = login(client).json()["refresh_token"]
    assert client.delete(f"/api/v1/users/{student['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/v1/users/{student['id']}", headers=admin).status_code == 404
    # The deleted account cannot refresh its session.
    assert (
        client.post("/api/v1/auth/refresh-token", json={"refresh_token": refresh}).status_code
        == 401
    )


def test_users_edit_only_their_own_profile(client):
    student = register(client).json()
    token = login(client).json()["access_token"]
    own = client.put(
        f"/api/v1/users/{student['id']}", json={"full_name": "خالد"}, headers=bearer(token)
    )
    assert own.status_code == 200 and own.json()["full_name"] == "خالد"
    assert client.put(f"/api/v1/users/{student['id']}", json={"role": "admin"},
                      headers=bearer(token)).status_code == 403  # fmt: skip
    other = register(client, username="sara", email="sara@example.com").json()
    assert client.put(f"/api/v1/users/{other['id']}", json={"full_name": "x"},
                      headers=bearer(token)).status_code == 403  # fmt: skip
    assert client.delete(f"/api/v1/users/{other['id']}", headers=bearer(token)).status_code == 403


def test_last_admin_is_protected(client):
    admin = admin_headers(client)
    me = client.get("/api/v1/auth/me", headers=admin).json()
    assert client.delete(f"/api/v1/users/{me['id']}", headers=admin).status_code == 409
    assert client.put(f"/api/v1/users/{me['id']}", json={"role": "faculty"},
                      headers=admin).status_code == 409  # fmt: skip
