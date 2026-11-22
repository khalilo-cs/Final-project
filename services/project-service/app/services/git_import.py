"""Import a project from a Git repository link (FR-02.1, FR-02.6).

The student may give an https link instead of a ZIP. The clone runs inside the
analysis job (it can take a while on a weak connection) and the result is
stored exactly like an uploaded ZIP, *with* its .git folder, so the Git history
analysis (FR-08.5) sees the real commits.

Safety: https only, hosts from an allow-list (no internal addresses can be
reached: no SSRF), a time limit, and size / file-count limits checked before
anything is kept.
"""

import concurrent.futures
import io
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings
from app.services import crypto_store

_PATH = re.compile(r"^(/[A-Za-z0-9_.\-]+){2,6}?(\.git)?/?$")
MAX_FILES = 20_000


class GitImportError(Exception):
    pass


def validate_url(url: str) -> str:
    parsed = urlparse(url.strip())
    allowed = {h.lower() for h in get_settings().git_allowed_hosts}
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in allowed:
        raise GitImportError("Only https links to: " + ", ".join(sorted(allowed)) + " are accepted")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise GitImportError("Links with credentials or ports are not accepted")
    if parsed.query or parsed.fragment or not _PATH.match(parsed.path) or ".." in parsed.path:
        raise GitImportError("Not a repository link (https://host/owner/repository)")
    return f"https://{parsed.hostname.lower()}{parsed.path.rstrip('/')}"


def _clone(url: str, target: Path) -> None:
    from dulwich import porcelain

    porcelain.clone(url, str(target), checkout=True, errstream=io.BytesIO())


def _zip(source: Path, archive: Path, max_bytes: int) -> None:
    total, count = 0, 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue  # a link could point outside the repository
            count += 1
            total += path.stat().st_size
            if count > MAX_FILES or total > max_bytes:
                limit = max_bytes // (1024 * 1024)
                raise GitImportError(f"The repository is over {limit} MB / {MAX_FILES} files")
            bundle.write(path, path.relative_to(source).as_posix())


def import_repository(url: str, archive: Path) -> None:
    """Clone `url` and store it at `archive` (a ZIP, encrypted at rest when configured)."""
    settings = get_settings()
    url = validate_url(url)
    work = Path(tempfile.mkdtemp(prefix="git-import-"))
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_clone, url, work / "repo")
        try:
            future.result(timeout=settings.git_clone_timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise GitImportError("Cloning took too long; upload a ZIP instead") from exc
        except GitImportError:
            raise
        except Exception as exc:  # noqa: BLE001 - dulwich raises many types
            raise GitImportError(f"Could not clone the repository ({type(exc).__name__})") from exc
        archive.parent.mkdir(parents=True, exist_ok=True)
        partial = archive.with_suffix(".partial")
        try:
            _zip(work / "repo", partial, settings.max_code_mb * 1024 * 1024)
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
        crypto_store.seal(archive)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        shutil.rmtree(work, ignore_errors=True)
