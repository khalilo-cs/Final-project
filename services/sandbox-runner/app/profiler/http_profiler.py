"""Performance measurements against a running app (plan, week 21)."""

import re
import statistics
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import httpx

# Tests may route through a transport; production uses the real network.
transport: httpx.BaseTransport | None = None
_LINK = re.compile(r"""href=["']([^"'#?]+)""", re.I)
MAX_PATHS = 8
MAX_BODY_BYTES = 1024 * 1024


def _client(timeout: float = 10) -> httpx.Client:
    # Never follow redirects: the runner also sits on the system's internal network, and a
    # student's app could redirect it to an internal service. A 3xx is measured as is.
    return httpx.Client(timeout=timeout, transport=transport, follow_redirects=False)


def _fetch(client: httpx.Client, url: str) -> tuple[int, bytes]:
    """(status, at most MAX_BODY_BYTES of the body): an endless response cannot fill
    the runner's memory."""
    with client.stream("GET", url) as response:
        body = bytearray()
        for piece in response.iter_bytes():
            body += piece
            if len(body) >= MAX_BODY_BYTES:
                break
        return response.status_code, bytes(body[:MAX_BODY_BYTES])


def wait_until_ready(base: str, timeout: float, alive: Callable[[], bool]) -> float | None:
    """Seconds until the app answers HTTP, or None if it never does / crashes."""
    started = time.monotonic()
    with _client(timeout=2) as client:
        while time.monotonic() - started < timeout:
            if not alive():
                return None
            try:
                _fetch(client, base + "/")
                return round(time.monotonic() - started, 2)
            except httpx.HTTPError:
                time.sleep(0.5)
    return None


def discover_paths(base: str) -> list[str]:
    paths = ["/"]
    try:
        with _client() as client:
            html = _fetch(client, base + "/")[1].decode("utf-8", errors="replace")
    except httpx.HTTPError:
        return paths
    host = urlparse(base).netloc
    for href in _LINK.findall(html):
        target = urlparse(urljoin(base + "/", href))
        if (
            target.netloc == host
            and target.path not in paths
            and not target.path.endswith((".css", ".js", ".png", ".jpg", ".svg", ".ico", ".woff2"))
        ):
            paths.append(target.path)
        if len(paths) >= MAX_PATHS:
            break
    return paths


def measure_endpoints(base: str, paths: list[str], repeat: int = 5) -> list[dict]:
    results = []
    with _client() as client:
        for path in paths:
            times, statuses = [], []
            for _ in range(repeat):
                start = time.perf_counter()
                try:
                    statuses.append(_fetch(client, base + path)[0])
                except httpx.HTTPError:
                    statuses.append(0)
                times.append((time.perf_counter() - start) * 1000)
            results.append(
                {
                    "path": path,
                    "status": max(set(statuses), key=statuses.count),
                    "avg_ms": round(statistics.mean(times), 1),
                    "max_ms": round(max(times), 1),
                }
            )
    return results


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def load_test(base: str, path: str, concurrency: int, total: int, timeout: float = 10) -> dict:
    latencies: list[float] = []
    errors = timeouts = 0

    def one(_):
        start = time.perf_counter()
        try:
            with _client(timeout) as client:
                status = _fetch(client, base + path)[0]
            return (time.perf_counter() - start) * 1000, status >= 500, False
        except httpx.TimeoutException:
            return None, True, True
        except httpx.HTTPError:
            return None, True, False

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for latency, failed, timed_out in pool.map(one, range(total)):
            if latency is not None:
                latencies.append(latency)
            errors += failed
            timeouts += timed_out
    elapsed = time.perf_counter() - started
    return {
        "concurrent_users": concurrency,
        "requests": total,
        "errors": errors,
        "timeouts": timeouts,
        "error_rate": round(errors / total, 3),
        "requests_per_second": round(total / elapsed, 1) if elapsed else None,
        "p50_ms": round(_percentile(latencies, 0.5), 1) if latencies else None,
        "p95_ms": round(_percentile(latencies, 0.95), 1) if latencies else None,
    }
