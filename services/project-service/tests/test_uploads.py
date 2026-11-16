import zlib

from app.services import uploads
from tests.test_grading import course  # noqa: F401  (fixture)
from tests.test_projects import make_zip

URL = "/api/v1/uploads"


def new(client, user, data: bytes, kind="code", filename="code.zip"):
    body = {"kind": kind, "filename": filename, "size": len(data)}
    return client.post(URL, json=body, headers=user.headers)


def piece(client, user, upload_id, offset, data, crc=None):
    headers = {**user.headers, "Upload-Offset": str(offset),
               "X-Chunk-CRC32": str(zlib.crc32(data) if crc is None else crc),
               "Content-Type": "application/octet-stream"}  # fmt: skip
    return client.patch(f"{URL}/{upload_id}", content=data, headers=headers)


def test_upload_survives_a_dropped_connection(client, users, course):  # noqa: F811
    student = users["student"]
    data = make_zip() * 40  # a few KB, sent in three pieces
    upload = new(client, student, data).json()
    third = len(data) // 3
    assert piece(client, student, upload["id"], 0, data[:third]).json()["offset"] == third

    # The connection drops mid-piece: the client does not know whether it arrived.
    assert piece(client, student, upload["id"], third, data[third : 2 * third]).status_code == 200
    again = piece(client, student, upload["id"], third, data[third : 2 * third])  # blind retry
    assert again.status_code == 409 and again.headers["Upload-Offset"] == str(2 * third)

    # After a restart the client asks where to continue.
    assert (
        client.get(f"{URL}/{upload['id']}", headers=student.headers).json()["offset"] == 2 * third
    )
    done = piece(client, student, upload["id"], 2 * third, data[2 * third :]).json()
    assert done["complete"] is True

    submitted = client.post(
        "/api/v1/projects",
        data={"title": "مشروع عبر رفع متقطع", "course_id": course["id"],
              "code_upload_id": upload["id"]},
        headers=student.headers,
    )  # fmt: skip
    assert submitted.status_code == 201, submitted.text
    assert not uploads.part_path(__import__("uuid").UUID(upload["id"])).exists()
    code = client.get(f"/api/v1/projects/{submitted.json()['id']}/code", headers=student.headers)
    assert code.content == data


def test_damaged_and_misplaced_pieces_are_rejected(client, users):
    student = users["student"]
    data = make_zip()
    upload = new(client, student, data).json()
    assert piece(client, student, upload["id"], 0, data[:50], crc=1).status_code == 422
    assert piece(client, student, upload["id"], 10, data[10:60]).status_code == 409
    assert piece(client, student, upload["id"], 0, data + b"extra").status_code == 400
    # Nothing was stored by the rejected pieces.
    assert client.get(f"{URL}/{upload['id']}", headers=student.headers).json()["offset"] == 0
    other = piece(client, users["other_student"], upload["id"], 0, data)
    assert other.status_code == 404


def test_limits_and_incomplete_uploads(client, users, course, monkeypatch):  # noqa: F811
    student = users["student"]
    assert new(client, student, b"x" * 10, filename="code.rar").status_code == 400
    assert new(client, users["faculty"], b"x" * 10).status_code == 403
    monkeypatch.setattr(uploads.get_settings(), "max_code_mb", 1)
    too_big = client.post(URL, json={"kind": "code", "filename": "a.zip", "size": 2_000_000},
                          headers=student.headers)  # fmt: skip
    assert too_big.status_code == 413

    data = make_zip()
    upload = new(client, student, data).json()
    piece(client, student, upload["id"], 0, data[:20])
    form = {"title": "ناقص", "course_id": course["id"], "code_upload_id": upload["id"]}
    assert client.post("/api/v1/projects", data=form, headers=student.headers).status_code == 409
    # The partial upload is still there to be continued.
    assert client.get(f"{URL}/{upload['id']}", headers=student.headers).json()["offset"] == 20
    missing = client.post("/api/v1/projects", headers=student.headers,
                          data={"title": "بلا كود", "course_id": course["id"]})  # fmt: skip
    assert missing.status_code == 422


def test_a_file_that_is_not_a_zip_is_refused_at_submission(client, users, course):  # noqa: F811
    student = users["student"]
    data = b"this is not a zip archive" * 10
    upload = new(client, student, data).json()
    piece(client, student, upload["id"], 0, data)
    form = {"title": "ليس ZIP", "course_id": course["id"], "code_upload_id": upload["id"]}
    assert client.post("/api/v1/projects", data=form, headers=student.headers).status_code == 400
