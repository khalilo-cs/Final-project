from app.services import result_cache
from tests.test_api import make_zip, upload


def test_identical_archive_is_served_from_cache(monkeypatch):
    archive = make_zip({"app.py": "def f(x):\n    return x + 1\n"})
    first = upload(archive)
    second = upload(archive)
    assert first.headers["X-Cache"] == "miss" and second.headers["X-Cache"] == "hit"
    assert first.json() == second.json()
    other = upload(make_zip({"app.py": "def g():\n    return 2\n"}))
    assert other.headers["X-Cache"] == "miss"


def test_new_rules_version_invalidates(monkeypatch):
    archive = make_zip({"a.py": "x = 1\n"})
    upload(archive)
    monkeypatch.setattr(result_cache, "RULES_VERSION", "next")
    assert upload(archive).headers["X-Cache"] == "miss"


def test_capacity_evicts_least_recently_used():
    for i in range(3):
        result_cache.put(f"d{i}", {"i": i}, capacity=2)
    assert result_cache.get("d0") is None and result_cache.get("d2") == {"i": 2}
    cached = result_cache.get("d2")
    cached["i"] = 99  # callers get a copy
    assert result_cache.get("d2") == {"i": 2}
