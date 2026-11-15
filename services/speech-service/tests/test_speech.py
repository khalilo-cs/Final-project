import sys
import time
import types

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.engines import (
    Disabled,
    LocalWhisper,
    RemoteWhisper,
    Transcript,
    TranscriptionError,
    get_engine,
)
from app.main import app

WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 64
SECRET = "test-secret-test-secret-test-secret-1234"


def token(role="student", kind="access"):
    claims = {"sub": "u1", "role": role, "type": kind, "exp": int(time.time()) + 600}
    return {"Authorization": f"Bearer {jwt.encode(claims, SECRET, algorithm='HS256')}"}


class FakeEngine:
    name = "fake"

    def __init__(self, duration=4.2, fail=False):
        self.calls = []
        self.duration, self.fail = duration, fail

    def available(self):
        return True, None

    def transcribe(self, audio, language, prompt):
        self.calls.append((audio, language, prompt))
        if self.fail:
            raise TranscriptionError("boom")
        return Transcript("استخدمت الاستعلامات المعدة", language, self.duration, self.name)


@pytest.fixture
def engine():
    fake = FakeEngine()
    app.dependency_overrides[get_engine] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


client = TestClient(app)


def post(audio=WEBM, headers=None, **data):
    return client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("answer.webm", audio, "audio/webm")},
        data=data,
        headers=token() if headers is None else headers,
    )


def test_needs_a_signed_in_user(engine):
    assert client.get("/api/v1/speech/status").status_code == 401
    assert post(headers={}).status_code == 401
    assert post(headers=token(kind="refresh")).status_code == 401


def test_transcribes_with_the_question_as_context(engine):
    response = post(language="ar", prompt="لماذا استخدمت PreparedStatement؟")
    assert response.status_code == 200
    assert response.json() == {
        "text": "استخدمت الاستعلامات المعدة", "language": "ar", "duration": 4.2, "engine": "fake",
    }  # fmt: skip
    assert engine.calls == [(WEBM, "ar", "لماذا استخدمت PreparedStatement؟")]
    assert post(language="auto").status_code == 200 and engine.calls[-1][1] is None


def test_rejects_non_audio_large_or_long_recordings(engine, monkeypatch):
    assert post(audio=b"<html>not audio</html>").status_code == 415
    assert post(audio=b"").status_code == 415
    monkeypatch.setattr(get_settings(), "max_audio_mb", 1)
    assert post(audio=WEBM + b"\x00" * (1024 * 1024)).status_code == 413
    engine.duration = 301
    assert post().status_code == 413
    assert post(language="fr").status_code == 422


def test_engine_failure_is_a_clean_error(engine):
    engine.fail = True
    assert post().status_code == 502


def test_status_reports_the_engine():
    app.dependency_overrides[get_engine] = Disabled
    try:
        body = client.get("/api/v1/speech/status", headers=token()).json()
        assert body["available"] is False and body["engine"] == "off"
        assert post().status_code == 503
    finally:
        app.dependency_overrides.clear()


def settings(**values):
    return Settings(jwt_secret=SECRET, **values)


def test_remote_engine_speaks_the_openai_transcription_api():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(200, json={"text": " مرحبا ", "language": "ar", "duration": 2.5})

    engine = RemoteWhisper(
        settings(speech_backend="remote", remote_url="http://whisper:8000", remote_api_key="k"),
        transport=httpx.MockTransport(handler),
    )
    assert engine.available() == (True, None)
    result = engine.transcribe(WEBM, "ar", "سؤال")
    assert (result.text, result.duration, result.engine) == ("مرحبا", 2.5, "remote")
    (request,) = seen
    assert request.url.path == "/v1/audio/transcriptions"
    assert request.headers["authorization"] == "Bearer k"
    body = request.content
    assert b'name="language"' in body and b'name="prompt"' in body and WEBM in body

    failing = RemoteWhisper(
        settings(remote_url="http://whisper:8000"),
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
    )
    with pytest.raises(TranscriptionError):
        failing.transcribe(WEBM, "ar", None)
    assert RemoteWhisper(settings()).available()[0] is False


def test_local_engine_loads_the_model_once(monkeypatch, tmp_path):
    loaded = []

    class FakeModel:
        def __init__(self, name, **options):
            loaded.append((name, options))

        def transcribe(self, audio, **options):
            assert options["language"] == "ar" and options["vad_filter"]
            segments = [types.SimpleNamespace(text=" أولاً "), types.SimpleNamespace(text="ثانياً")]
            return iter(segments), types.SimpleNamespace(language="ar", duration=3.14159)

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel)
    )
    engine = LocalWhisper(settings(whisper_model="tiny", whisper_model_dir=str(tmp_path)))
    assert engine.available() == (True, None)
    first = engine.transcribe(WEBM, "ar", None)
    engine.transcribe(WEBM, "ar", None)
    assert (first.text, first.duration) == ("أولاً ثانياً", 3.14)
    assert len(loaded) == 1 and loaded[0][0] == "tiny"


def test_local_engine_without_the_library(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert LocalWhisper(settings()).available()[0] is False
