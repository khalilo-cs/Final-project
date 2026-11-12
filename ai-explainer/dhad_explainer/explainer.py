"""خط أنابيب الشرح: خطأ حتمي من المترجم ← موجّه مقيَّد ← مزود ← حارس ← عرض (أو احتياطي)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import guard, prompt
from .knowledge import REPO
from .providers import OfflineProvider, ProviderError


@dataclass
class Explanation:
    text: str
    level: int
    provider: str
    model: str
    cached: bool = False
    fallback_used: bool = False
    guard_ok: bool = True
    guard_reasons: list[str] = field(default_factory=list)
    error_reason: str | None = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def dhad_binary() -> str | None:
    env = os.environ.get("DHAD_BIN")
    if env:
        return env
    builds = [p for p in (REPO / "target" / "release" / "dhad", REPO / "target" / "debug" / "dhad") if p.exists()]
    if builds:
        return str(max(builds, key=lambda p: p.stat().st_mtime))
    return shutil.which("dhad")


class Cache:
    """ذاكرة مؤقتة للشروح: الأخطاء الشائعة تتكرر، فلا داعي لطلب النموذج كل مرة."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self.data: dict[str, dict] = {}
        if self.path and self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def key(provider: str, model: str, error: dict, source: str, level: int) -> str:
        line = error.get("line") or 1
        snippet = prompt.numbered_snippet(source, line)
        raw = json.dumps([provider, model, level, error["code"], error["message"], snippet], ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, k: str) -> dict | None:
        return self.data.get(k)

    def put(self, k: str, v: dict) -> None:
        self.data[k] = v
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")


def explain(error: dict, source: str, level: int, provider, cache: Cache | None = None,
            dhad_bin: str | None = None) -> Explanation:
    """شرح خطأ واحد بمستوى واحد. لا يرمي استثناءً: عند أي فشل يعيد الشرح الحتمي."""
    offline = OfflineProvider()
    model = getattr(provider, "model", provider.name)
    start = time.perf_counter()

    if isinstance(provider, OfflineProvider):
        text = offline.explain(error, source, level)
        return Explanation(text, level, "offline", "docs", latency_ms=(time.perf_counter() - start) * 1000)

    k = Cache.key(provider.name, model, error, source, level)
    if cache and (hit := cache.get(k)):
        return Explanation(hit["text"], level, provider.name, model, cached=True,
                           latency_ms=(time.perf_counter() - start) * 1000)

    try:
        text = provider.generate(prompt.system_prompt(), prompt.user_message(error, source, level))
    except ProviderError as e:
        return Explanation(offline.explain(error, source, level), level, provider.name, model,
                           fallback_used=True, error_reason=str(e),
                           latency_ms=(time.perf_counter() - start) * 1000)

    g = guard.check(text, error, level, dhad_bin)
    latency = (time.perf_counter() - start) * 1000
    if not g.ok:
        return Explanation(offline.explain(error, source, level), level, provider.name, model,
                           fallback_used=True, guard_ok=False, guard_reasons=g.reasons, latency_ms=latency)
    if cache:
        cache.put(k, {"text": text})
    return Explanation(text, level, provider.name, model, latency_ms=latency)


def first_error(path: str | Path, dhad_bin: str) -> tuple[dict | None, str]:
    """أول خطأ (ثابت ثم وقت التشغيل) في الملف، مع النص المطبَّع."""
    check = subprocess.run([dhad_bin, "افحص", "--json", str(path)], capture_output=True, text=True)
    data = json.loads(check.stdout)
    errors = [d for d in data["diagnostics"] if d["severity"] == "error"]
    if errors:
        return errors[0], data["source"]
    run = subprocess.run([dhad_bin, "شغّل", "--json", "--وقود", "5000000", str(path)],
                         capture_output=True, text=True, timeout=60)
    data = json.loads(run.stdout)
    return (data["diagnostics"][0] if data["diagnostics"] else None), data["source"]


def explain_file(path: str | Path, levels: list[int], provider, cache: Cache | None = None
                 ) -> tuple[dict | None, list[Explanation]]:
    dhad = dhad_binary()
    if not dhad:
        raise FileNotFoundError("لم يُعثر على الأمر dhad — ابنِه بـ cargo build أو اضبط DHAD_BIN")
    error, source = first_error(path, dhad)
    if error is None:
        return None, []
    return error, [explain(error, source, lv, provider, cache, dhad) for lv in levels]
