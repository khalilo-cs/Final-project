"""قاعدة المعرفة: صفحات docs/errors الرسمية (مصدر الحقيقة الوحيد للشرح)."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs" / "errors"


@lru_cache(maxsize=1)
def pages(docs_dir: str | None = None) -> dict[int, str]:
    d = Path(docs_dir) if docs_dir else DOCS
    out: dict[int, str] = {}
    for p in sorted(d.glob("[0-9][0-9][0-9][0-9].md")):
        out[int(p.stem)] = p.read_text(encoding="utf-8")
    if not out:
        raise FileNotFoundError(f"لا توجد صفحات توثيق في {d} — شغّل tools/gen_error_docs.py")
    return out


def page(code: int) -> str | None:
    return pages().get(code)


def section(md: str, heading: str) -> str:
    """نص قسم «## العنوان» من صفحة توثيق."""
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1).strip() if m else ""


def code_blocks(md: str) -> list[str]:
    return [b.strip() for b in re.findall(r"```dhad\n(.*?)```", md, re.S)]


def reference_text() -> str:
    """كل الصفحات مرتبة ترتيبًا ثابتًا: جزء ثابت من موجّه النظام قابل للتخزين المؤقت."""
    return "\n\n".join(pages()[c] for c in sorted(pages()))
