import base64
import os
from pathlib import Path

import pytest

from app.config import get_settings
from app.services import crypto_store
from tests.test_projects import course, make_zip, submit  # noqa: F401 - fixture

KEY = base64.b64encode(bytes(range(32))).decode()


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_encryption_key", KEY)


def test_round_trip_across_chunks(tmp_path, key):
    data = os.urandom(crypto_store.CHUNK * 2 + 123)
    path = tmp_path / "code.zip"
    path.write_bytes(data)
    crypto_store.seal(path)
    raw = path.read_bytes()
    assert raw.startswith(crypto_store.MAGIC) and data[:64] not in raw
    assert crypto_store.read_bytes(path) == data
    crypto_store.seal(path)  # sealing twice is a no-op
    assert crypto_store.read_bytes(path) == data


def test_tampering_and_truncation_are_detected(tmp_path, key):
    path = tmp_path / "report.pdf"
    path.write_bytes(os.urandom(crypto_store.CHUNK + 10))
    crypto_store.seal(path)
    raw = bytearray(path.read_bytes())
    flipped = tmp_path / "flipped.pdf"
    raw[40] ^= 1
    flipped.write_bytes(raw)
    with pytest.raises(crypto_store.EncryptionError, match="tampered"):
        crypto_store.read_bytes(flipped)
    # Dropping the last chunk: the previous one was not marked as final.
    first_chunk_end = len(crypto_store.MAGIC) + 8 + 4 + crypto_store.CHUNK + 16
    cut = tmp_path / "cut.pdf"
    cut.write_bytes(path.read_bytes()[:first_chunk_end])
    with pytest.raises(crypto_store.EncryptionError):
        crypto_store.read_bytes(cut)


def test_wrong_or_missing_key(tmp_path, key, monkeypatch):
    path = tmp_path / "a.sql"
    path.write_bytes(b"CREATE TABLE t (id INT);")
    crypto_store.seal(path)
    monkeypatch.setattr(get_settings(), "storage_encryption_key", "")
    with pytest.raises(crypto_store.EncryptionError, match="not set"):
        crypto_store.read_bytes(path)
    monkeypatch.setattr(
        get_settings(), "storage_encryption_key", base64.b64encode(b"x" * 16).decode()
    )
    with pytest.raises(crypto_store.EncryptionError, match="32 bytes"):
        crypto_store.read_bytes(path)


def test_no_key_means_plain_files(tmp_path):
    path = tmp_path / "x.zip"
    path.write_bytes(b"PK\x03\x04data")
    crypto_store.seal(path)
    assert path.read_bytes() == b"PK\x03\x04data"


def test_uploaded_files_are_encrypted_on_disk(client, users, course, analyzer, key):  # noqa: F811
    code = make_zip()
    response = submit(client, users["student"], course["id"], code=code)
    assert response.status_code == 201, response.text
    stored = Path(get_settings().storage_dir).resolve() / response.json()["id"] / "code.zip"
    assert stored.read_bytes().startswith(crypto_store.MAGIC)
    # The analyzer still received the original archive.
    assert code in analyzer.calls[0].content
    # And the owner downloads the original too.
    download = client.get(
        f"/api/v1/projects/{response.json()['id']}/code", headers=users["student"].headers
    )
    assert download.status_code == 200 and download.content == code
