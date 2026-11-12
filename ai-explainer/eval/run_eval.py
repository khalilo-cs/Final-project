#!/usr/bin/env python3
"""تقييم شارح الأخطاء: كل كود خطأ × أربعة مستويات × كل مزود.

يُنتج في eval/results/:
- <مزود>.jsonl: كل شرح مع نتيجة الحارس وأسباب الرفض والزمن.
- summary.md: معدل اجتياز الحارس، أسباب الرفض، والزمن لكل مزود.
- rating_sheet.csv + rating_key.json: ورقة تقييم بشري مزدوج التعمية (المزود مخفي والترتيب عشوائي).

الاستخدام: python3 eval/run_eval.py --providers offline claude ollama
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from dhad_explainer import knowledge  # noqa: E402
from dhad_explainer.explainer import Cache, dhad_binary, explain  # noqa: E402
from dhad_explainer.levels import LEVELS  # noqa: E402
from dhad_explainer.providers import make  # noqa: E402

REPO = HERE.parents[1]


def cases(dhad: str) -> list[tuple[dict, str]]:
    """حالة لكل كود: البرنامج الخاطئ من صفحة توثيقه، والخطأ كما يصدره المترجم فعلًا."""
    out = []
    for code, md in sorted(knowledge.pages().items()):
        if code >= 3000:
            continue  # التحذيرات وقيود المولّد خارج نطاق شرح المبتدئ
        bad = knowledge.code_blocks(md)[0]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "برنامج.ضاد"
            f.write_text(bad + "\n", encoding="utf-8")
            check = json.loads(subprocess.run([dhad, "افحص", "--json", str(f)], capture_output=True, text=True).stdout)
            errs = [x for x in check["diagnostics"] if x["severity"] == "error"]
            if not errs:
                run = subprocess.run([dhad, "شغّل", "--json", "--وقود", "100000", str(f)], capture_output=True, text=True)
                errs = json.loads(run.stdout)["diagnostics"]
                src = json.loads(run.stdout)["source"]
            else:
                src = check["source"]
        err = next((e for e in errs if e["code"] == code), errs[0] if errs else None)
        if err:
            out.append((err, src))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", nargs="+", default=["offline"])
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    dhad = dhad_binary()
    res_dir = HERE / "results"
    res_dir.mkdir(exist_ok=True)
    all_cases = cases(dhad)
    rows_by_provider: dict[str, list[dict]] = {}

    for name in args.providers:
        provider = make(name)
        cache = Cache(res_dir / f"cache-{name}.json")
        rows = []
        for err, src in all_cases:
            for level in LEVELS:
                r = explain(err, src, level, provider, cache, dhad)
                rows.append({"code": err["code"], "message": err["message"], "line": err.get("line"),
                             "source": src, **r.to_dict()})
            print(f"  {name}: ضاد-{err['code']:04d} ✔", file=sys.stderr)
        rows_by_provider[name] = rows
        with open(res_dir / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    md = ["# نتائج تقييم شارح الأخطاء", "",
          f"{len(all_cases)} كود خطأ × {len(LEVELS)} مستويات لكل مزود.", "",
          "| المزود | الشروح | اجتاز الحارس | احتياطي (فشل المزود) | رُفض من الحارس | وسيط الزمن (ms) |",
          "|---|---:|---:|---:|---:|---:|"]
    reasons_md = []
    for name, rows in rows_by_provider.items():
        n = len(rows)
        guard_fail = sum(1 for r in rows if not r["guard_ok"])
        provider_fail = sum(1 for r in rows if r["fallback_used"] and r["guard_ok"])
        passed = n - guard_fail - provider_fail
        lat = statistics.median(r["latency_ms"] for r in rows if not r["cached"]) if any(not r["cached"] for r in rows) else 0
        md.append(f"| {name} | {n} | {passed} ({passed / n:.0%}) | {provider_fail} | {guard_fail} | {lat:.0f} |")
        counts = Counter(reason.split(" (")[0] for r in rows for reason in r["guard_reasons"])
        if counts:
            reasons_md += [f"### أسباب الرفض — {name}", ""] + [f"- {k}: {v}" for k, v in counts.most_common()] + [""]
        errs = Counter(r["error_reason"] for r in rows if r["error_reason"])
        if errs:
            reasons_md += [f"### أسباب فشل المزود — {name}", ""] + [f"- {k}: {v}" for k, v in errs.most_common()] + [""]
    (res_dir / "summary.md").write_text("\n".join(md + [""] + reasons_md), encoding="utf-8")

    items = [(name, r) for name, rows in rows_by_provider.items() for r in rows]
    random.Random(args.seed).shuffle(items)
    key = {}
    with open(res_dir / "rating_sheet.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["المعرف", "الكود", "المستوى", "رسالة الخطأ", "الشرح", "الدقة (١-٥)", "البساطة (١-٥)", "سلامة العربية (١-٥)"])
        for i, (name, r) in enumerate(items, 1):
            key[i] = name
            w.writerow([i, f"ضاد-{r['code']:04d}", LEVELS[r["level"]].title, r["message"], r["text"], "", "", ""])
    (res_dir / "rating_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
