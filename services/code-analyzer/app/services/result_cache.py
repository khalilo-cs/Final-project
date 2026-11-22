"""Results of identical archives are reused (NFR-03: caching of repeated results).

Re-running an analysis, or a student re-submitting the same ZIP, costs nothing.
The key is the archive's SHA-256 plus RULES_VERSION, so changing the analyzers
(bump the version) never serves stale findings. In memory, least recently used
entries leave first.
"""

import copy
import threading
from collections import OrderedDict

RULES_VERSION = "2026-11-22"

_lock = threading.Lock()
_entries: OrderedDict[str, dict] = OrderedDict()


def key(sha256: str) -> str:
    return f"{RULES_VERSION}:{sha256}"


def get(digest: str) -> dict | None:
    with _lock:
        value = _entries.get(key(digest))
        if value is None:
            return None
        _entries.move_to_end(key(digest))
        return copy.deepcopy(value)


def put(digest: str, value: dict, capacity: int) -> None:
    if capacity <= 0:
        return
    with _lock:
        _entries[key(digest)] = copy.deepcopy(value)
        _entries.move_to_end(key(digest))
        while len(_entries) > capacity:
            _entries.popitem(last=False)


def clear() -> None:
    with _lock:
        _entries.clear()
