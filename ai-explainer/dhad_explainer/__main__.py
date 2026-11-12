"""واجهة سطر الأوامر: python -m dhad_explainer ملف.ضاد [--مستوى 1..4 | --كل] [--مزود claude|ollama|offline]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .explainer import Cache, explain_file
from .levels import LEVELS
from .providers import make


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dhad-explain", description="شرح أخطاء برامج ضاد بالعربية للمبتدئين")
    ap.add_argument("file", help="ملف .ضاد")
    ap.add_argument("--level", "--مستوى", type=int, choices=[1, 2, 3, 4], default=1, help="مستوى التلميح")
    ap.add_argument("--all", "--كل", action="store_true", help="كل المستويات بالترتيب")
    ap.add_argument("--provider", "--مزود", default=os.environ.get("DHAD_EXPLAINER", "claude"),
                    choices=["claude", "ollama", "offline"])
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "dhad-explainer" / "cache.json"))
    ap.add_argument("--json", action="store_true", help="مخرجات JSON")
    args = ap.parse_args(argv)

    try:
        provider = make(args.provider)
    except Exception as e:  # مثلًا: حزمة anthropic غير مثبتة
        print(f"تعذّر تهيئة المزود «{args.provider}»: {e} — سيُستخدم الشرح من التوثيق.", file=sys.stderr)
        provider = make("offline")
    levels = [1, 2, 3, 4] if args.all else [args.level]
    error, results = explain_file(args.file, levels, provider, Cache(args.cache))

    if args.json:
        print(json.dumps({"error": error, "explanations": [r.to_dict() for r in results]}, ensure_ascii=False, indent=1))
        return 0
    if error is None:
        print("✔ لا أخطاء في البرنامج.")
        return 0
    print(f"خطأ[{error['codeStr']}]: {error['message']}" + (f" — السطر {error['line']}" if error.get("line") else ""))
    for r in results:
        tag = "من التوثيق" if r.provider == "offline" or r.fallback_used else f"{r.provider}/{r.model}"
        print(f"\n— {LEVELS[r.level].title} ({tag}{'، من الذاكرة المؤقتة' if r.cached else ''})")
        print(r.text)
        if r.fallback_used:
            why = r.error_reason or "، ".join(r.guard_reasons)
            print(f"  [عُرض الشرح من التوثيق لأن: {why}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
