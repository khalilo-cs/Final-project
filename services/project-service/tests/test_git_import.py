import io
import uuid
import zipfile

import pytest

from app import database
from app.models.project import Project
from app.services import crypto_store, git_import
from tests.test_projects import course  # noqa: F401 - fixture


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",  # not https
        "https://localhost/a/b",  # not an allowed host (SSRF)
        "https://169.254.169.254/latest/meta-data",
        "https://github.com.evil.example/a/b",
        "https://user:pw@github.com/a/b",
        "https://github.com:8443/a/b",
        "https://github.com/a",  # no repository part
        "https://github.com/a/b?x=1",
        "https://github.com/a/../b",
    ],
)
def test_bad_links_are_refused(url):
    with pytest.raises(git_import.GitImportError):
        git_import.validate_url(url)


def test_good_link_is_normalized():
    assert git_import.validate_url("https://GitHub.com/ali/library-system.git/") == (
        "https://github.com/ali/library-system.git"
    )


def fake_clone(url, target):
    from dulwich import porcelain

    target.mkdir(parents=True)
    repo = porcelain.init(str(target))
    config = repo.get_config()
    config.set(b"commit", b"gpgsign", False)  # ignore any signing in the machine's git config
    config.write_to_path()
    (target / "main.py").write_text("def main():\n    return 1\n")
    porcelain.add(repo, [str(target / "main.py")])
    porcelain.commit(repo, message=b"first", author=b"Ali <a@x>", committer=b"Ali <a@x>")


def test_submission_by_git_link_is_cloned_and_analyzed(
    client, users, course, analyzer, monkeypatch
):  # noqa: F811
    monkeypatch.setattr(git_import, "_clone", fake_clone)
    response = client.post(
        "/api/v1/projects",
        data={"title": "Library", "course_id": course["id"],
              "git_url": "https://github.com/ali/library"},
        headers=users["student"].headers,
    )  # fmt: skip
    assert response.status_code == 201, response.text
    with database.SessionLocal() as db:
        project = db.get(Project, uuid.UUID(response.json()["id"]))
        assert project.status.value == "analyzed"
        archive = crypto_store.read_bytes(project.code_path)
    names = zipfile.ZipFile(io.BytesIO(archive)).namelist()
    assert "main.py" in names and any(n.startswith(".git/") for n in names)  # history kept
    assert analyzer.calls  # the code analyzer received it


def test_failed_clone_marks_the_project(client, users, course, monkeypatch):  # noqa: F811
    def boom(url, target):
        raise OSError("network unreachable")

    monkeypatch.setattr(git_import, "_clone", boom)
    response = client.post(
        "/api/v1/projects",
        data={"title": "X", "course_id": course["id"], "git_url": "https://gitlab.com/a/b"},
        headers=users["student"].headers,
    )
    status = client.get(f"/api/v1/projects/{response.json()['id']}/status",
                        headers=users["student"].headers).json()  # fmt: skip
    assert status["status"] == "analysis_failed" and "Git import failed" in status["analysis_error"]


def test_bad_link_is_rejected_at_submission(client, users, course):  # noqa: F811
    response = client.post(
        "/api/v1/projects",
        data={"title": "X", "course_id": course["id"], "git_url": "https://localhost/a/b"},
        headers=users["student"].headers,
    )
    assert response.status_code == 422
