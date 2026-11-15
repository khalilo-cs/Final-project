"""A stand-in for Docker: runs a *trusted* local test server with chosen behaviour."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.sandbox.backend import Backend, BuildFailed


def make_server(mode: str) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            if mode == "slow":
                time.sleep(0.4)
            if mode == "errors" and self.path == "/":
                self.send_response(500)
                self.end_headers()
                return
            body = b'<a href="/books">books</a> <a href="/about">about</a> <a href="https://x.org/">x</a>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class FakeBackend(Backend):
    instances: list["FakeBackend"] = []

    def __init__(self, mode: str = "fast") -> None:
        self.mode = mode
        self.cleaned = False
        self.memory = 50.0
        FakeBackend.instances.append(self)

    def prepare(self, run_id, plan, project):
        if self.mode == "build_fails":
            raise BuildFailed("Build failed", "ERROR: No matching distribution for flaskk")
        return {"plan": plan}

    def start(self, handle, plan):
        if self.mode == "crash":
            handle["server"] = None
            return "http://127.0.0.1:9"  # nothing listens there
        handle["server"] = make_server(self.mode)
        return f"http://127.0.0.1:{handle['server'].server_address[1]}"

    def running(self, handle):
        return handle.get("server") is not None

    def stats(self, handle):
        if self.mode == "leak":
            self.memory += 60
        return {"memory_mb": self.memory, "cpu_percent": 12.5}

    def logs(self, handle):
        return (
            "Traceback: ImportError: No module named 'flask_sqlalchemy'"
            if self.mode == "crash"
            else ""
        )

    def cleanup(self, handle):
        if handle.get("server"):
            handle["server"].shutdown()
        self.cleaned = True
