import httpx

from app.knowledge import store
from app.models import KnowledgeSource
from tests.conftest import token

PAGE = """<html><head><title>SQL Injection Prevention</title><script>x()</script></head>
<body><nav>menu</nav><h1>Use prepared statements</h1>
<p>Parameterized queries keep data separate from SQL code, so user input cannot change
the query.</p></body></html>"""


def fake_web(robots="User-agent: *\nAllow: /", status=200):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return httpx.Response(status, text=PAGE, headers={"content-type": "text/html"})

    return httpx.MockTransport(handler)


def test_ingest_and_search(client, people, monkeypatch):
    monkeypatch.setattr(store, "transport", fake_web())
    monkeypatch.setattr(store, "check_public_address", False)
    faculty = token(people["faculty"], "faculty")
    url = "https://cheatsheetseries.owasp.org/sql.html"
    assert client.post("/api/v1/ai/knowledge/sources", json={"url": url},
                       headers=token(people["student"], "student")).status_code == 403  # fmt: skip
    assert (
        client.post("/api/v1/ai/knowledge/sources", json={"url": url}, headers=faculty).status_code
        == 202
    )
    (source,) = client.get("/api/v1/ai/knowledge/sources", headers=faculty).json()
    assert source["status"] == "indexed" and source["items"] == 1
    hits = client.get("/api/v1/ai/knowledge/search", params={"q": "parameterized queries"},
                      headers=faculty).json()  # fmt: skip
    assert hits[0]["title"] == "SQL Injection Prevention"
    assert "menu" not in hits[0]["text"] and "x()" not in hits[0]["text"]


def test_robots_and_url_rules(db, monkeypatch, people):
    monkeypatch.setattr(store, "check_public_address", False)
    monkeypatch.setattr(store, "transport", fake_web(robots="User-agent: *\nDisallow: /"))

    def run(url):
        source = KnowledgeSource(url=url, added_by=people["faculty"])
        db.add(source)
        db.commit()
        store.ingest_url(db, source)
        return source

    assert "robots.txt" in run("https://example.org/page").error
    assert "https" in run("http://example.org/plain").error

    monkeypatch.setattr(store, "check_public_address", True)
    assert "non-public" in run("https://localhost/admin").error  # SSRF guard
