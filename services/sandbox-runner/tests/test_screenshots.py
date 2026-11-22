import base64
import http.server
import threading

import pytest

from app.profiler import screenshots


def test_no_playwright_means_no_screenshots(monkeypatch):
    monkeypatch.setattr(screenshots, "available", lambda: False)
    assert screenshots.capture("http://127.0.0.1:1", [{"path": "/", "status": 200}]) == []


def test_only_pages_that_answered_are_captured(monkeypatch):
    monkeypatch.setattr(screenshots, "available", lambda: True)
    assert screenshots.capture("http://127.0.0.1:1", [{"path": "/", "status": 500}]) == []


@pytest.mark.skipif(not screenshots.available(), reason="Playwright is not installed")
def test_real_screenshot_blocks_outside_hosts():
    seen: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append(self.path)
            body = (
                b"<html><head><title>Shop</title></head><body><h1>Hi</h1>"
                b'<img src="http://example.invalid/track.png"></body></html>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        shots = screenshots.capture(base, [{"path": "/", "status": 200}])
    finally:
        server.shutdown()
    assert len(shots) == 1 and shots[0]["title"] == "Shop"
    assert base64.b64decode(shots[0]["image_jpeg_base64"])[:3] == b"\xff\xd8\xff"  # JPEG
