"""LDAP sign-in against ldap3's offline mock directory."""

import pytest
from ldap3 import MOCK_SYNC, OFFLINE_AD_2012_R2, Connection, Server

from app.config import get_settings
from app.services import ldap_auth
from tests.test_auth import bearer, login, register

BASE = "ou=people,dc=su,dc=edu,dc=ye"
SERVICE = "cn=mihakk,ou=services,dc=su,dc=edu,dc=ye"


@pytest.fixture
def directory(monkeypatch):
    server = Server("mock", get_info=OFFLINE_AD_2012_R2)
    seed = Connection(server, client_strategy=MOCK_SYNC)
    seed.strategy.add_entry(SERVICE, {"userPassword": "service-pass", "objectClass": "person"})
    seed.strategy.add_entry(
        f"cn=Ali Saleh,{BASE}",
        {"sAMAccountName": "ali", "userPassword": "ali-dir-pass", "mail": "ali@su.edu.ye",
         "displayName": "علي صالح", "employeeNumber": "2022777", "objectClass": "person"},
    )  # fmt: skip
    seed.strategy.add_entry(
        f"cn=Dr Huda,{BASE}",
        {"sAMAccountName": "huda", "userPassword": "huda-dir-pass", "mail": "huda@su.edu.ye",
         "displayName": "د. هدى", "objectClass": "person",
         "memberOf": ["CN=CS-Faculty,OU=Groups,DC=su,DC=edu,DC=ye"]},
    )  # fmt: skip

    def factory():
        return server

    # Mock connections share the server's in-memory directory.
    monkeypatch.setattr(ldap_auth, "server_factory", factory)
    monkeypatch.setattr(ldap_auth, "connection_strategy", MOCK_SYNC)
    s = get_settings()
    for name, value in {
        "ldap_url": "ldaps://dc.su.edu.ye",
        "ldap_bind_dn": SERVICE,
        "ldap_bind_password": "service-pass",
        "ldap_base_dn": BASE,
        "ldap_user_filter": "(sAMAccountName={username})",
        "ldap_student_id_attribute": "employeeNumber",
        "ldap_faculty_groups": ["CS-Faculty"],
    }.items():
        monkeypatch.setattr(s, name, value)
    return seed


def me(client, response):
    assert response.status_code == 200, response.text
    return client.get("/api/v1/auth/me", headers=bearer(response.json()["access_token"])).json()


def test_directory_student_signs_in_and_is_created(client, directory):
    user = me(client, login(client, "ali", "ali-dir-pass"))
    assert user["role"] == "student" and user["email"] == "ali@su.edu.ye"
    assert user["full_name"] == "علي صالح" and user["student_id"] == "2022777"
    # Second sign-in reuses the same account.
    assert me(client, login(client, "ali", "ali-dir-pass"))["id"] == user["id"]


def test_faculty_group_maps_to_faculty(client, directory):
    assert me(client, login(client, "huda", "huda-dir-pass"))["role"] == "faculty"


def test_wrong_and_empty_passwords_are_rejected(client, directory):
    assert login(client, "ali", "wrong-password").status_code == 401
    # An empty password would be an "unauthenticated bind" on many servers.
    assert client.post(
        "/api/v1/auth/login", json={"username": "ali", "password": ""}
    ).status_code in (401, 422)
    assert login(client, "nobody", "whatever-pass").status_code == 401


def test_filter_injection_does_not_match_other_users(client, directory):
    assert login(client, "*", "ali-dir-pass").status_code == 401
    assert login(client, "ali)(sAMAccountName=*", "ali-dir-pass").status_code == 401


def test_local_accounts_still_work_with_ldap_enabled(client, directory):
    assert register(client).status_code == 201
    assert login(client).status_code == 200  # khalid is a local account
    assert login(client, "admin", "admin-password-1").status_code == 200


def test_directory_never_takes_over_a_local_username(client, directory):
    # Someone registered "ali" locally with another e-mail before the university joined.
    assert register(client, username="ali", email="squatter@example.com").status_code == 201
    # The local account keeps its own password ...
    assert login(client, "ali", "s3cure-pass").status_code == 200
    # ... and the directory password does not open it.
    assert login(client, "ali", "ali-dir-pass").status_code == 401
