"""Screenshots of the running project's pages (FR-09.8).

A headless Chromium opens the pages the profiler already found. The browser may
only talk to the sandboxed project itself: every request to another host is
aborted, so a student page cannot make the runner fetch anything outside.
Playwright is optional (a build argument of the image); without it the run
simply has no screenshots.
"""

import base64
import logging
from urllib.parse import urlparse

log = logging.getLogger(__name__)

MAX_SHOTS = 3
VIEWPORT = {"width": 1280, "height": 800}
PAGE_TIMEOUT_MS = 10_000


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def capture(base: str, endpoints: list[dict], limit: int = MAX_SHOTS) -> list[dict]:
    """JPEG screenshots (base64) of up to `limit` pages that answered 200."""
    paths = [e["path"] for e in endpoints if e.get("status") == 200][:limit]
    if not paths or not available():
        return []
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    host = urlparse(base).netloc
    shots: list[dict] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(
                viewport=VIEWPORT, java_script_enabled=True, accept_downloads=False
            )
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if urlparse(route.request.url).netloc == host
                    else route.abort()
                ),
            )
            page = context.new_page()
            page.set_default_timeout(PAGE_TIMEOUT_MS)
            for path in paths:
                try:
                    page.goto(base + path, wait_until="load")
                    image = page.screenshot(type="jpeg", quality=60, full_page=False)
                except PlaywrightError as exc:
                    log.info("screenshot of %s failed: %s", path, exc)
                    continue
                shots.append(
                    {
                        "path": path,
                        "title": (page.title() or "")[:200],
                        "image_jpeg_base64": base64.b64encode(image).decode(),
                    }
                )
            browser.close()
    except Exception as exc:  # noqa: BLE001 - screenshots are a bonus, never fail the run
        log.warning("screenshots unavailable: %s", exc)
    return shots
