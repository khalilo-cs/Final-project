"""حارس الجودة: فحوص آلية على شرح النموذج قبل عرضه للطالب.

أي شرح لا يجتاز كل الفحوص يُرفض، ويُعرض بدلًا منه الشرح الحتمي المأخوذ من التوثيق.
معدل الرفض وأسبابه مقياس في التقييم.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .levels import LEVELS

ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿ]")
LATIN = re.compile(r"[A-Za-z]")
CODE_BLOCK = re.compile(r"```(\w*)\n?(.*?)```", re.S)
ERROR_CODE = re.compile(r"ضاد-(\d{4}|[٠-٩]{4})")
LINE_REF = re.compile(r"السطر\s+([0-9٠-٩]+)")
UNSAFE = re.compile(r"<\s*script|javascript:|<\s*iframe|on\w+\s*=", re.I)

EASTERN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


@dataclass
class GuardResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def _prose(text: str) -> str:
    return CODE_BLOCK.sub(" ", text)


def check(text: str, error: dict, level: int, dhad_bin: str | None = None) -> GuardResult:
    lv = LEVELS[level]
    reasons: list[str] = []
    prose = _prose(text).strip()

    if not prose:
        reasons.append("فارغ")
    if UNSAFE.search(text):
        reasons.append("محتوى غير آمن")

    ar, la = len(ARABIC.findall(prose)), len(LATIN.findall(prose))
    if ar + la and ar / (ar + la) < 0.85:
        reasons.append("ليس بالعربية أساسًا")

    words = len(prose.split())
    if words > lv.max_words:
        reasons.append(f"طويل ({words} كلمة > {lv.max_words})")

    blocks = CODE_BLOCK.findall(text)
    lo, hi = lv.code_blocks
    if not lo <= len(blocks) <= hi:
        reasons.append(f"عدد كتل الكود {len(blocks)} خارج [{lo}، {hi}]")

    actual = int(error["code"])
    for m in ERROR_CODE.findall(text):
        if int(m.translate(EASTERN)) != actual:
            reasons.append(f"يذكر كود خطأ آخر ضاد-{m}")

    line = error.get("line")
    refs = [int(x.translate(EASTERN)) for x in LINE_REF.findall(prose)]
    if line and any(r != line for r in refs):
        reasons.append(f"يذكر سطرًا غير السطر {line}")
    if lv.needs_line and line and line not in refs:
        reasons.append(f"لا يذكر السطر {line}")

    if dhad_bin and blocks:
        for lang, body in blocks:
            if lang not in ("", "dhad", "ضاد"):
                reasons.append(f"كتلة كود بلغة أخرى ({lang})")
                continue
            if syntax_error(body, dhad_bin):
                reasons.append("كتلة الكود ليست ضادًا صحيحًا نحويًا")

    return GuardResult(ok=not reasons, reasons=reasons)


def syntax_error(code: str, dhad_bin: str) -> bool:
    """هل في الكود خطأ نحوي (أكواد ٠٠٠١–٠٩٩٩)؟ الأخطاء الدلالية مقبولة في مقتطف منفرد."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "مقتطف.ضاد"
        f.write_text(code, encoding="utf-8")
        r = subprocess.run([dhad_bin, "افحص", "--json", str(f)], capture_output=True, text=True)
    try:
        diags = json.loads(r.stdout)["diagnostics"]
    except (json.JSONDecodeError, KeyError):
        return True
    return any(d["code"] < 1000 for d in diags)
