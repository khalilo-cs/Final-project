#!/usr/bin/env python3
"""توليد صفحات توثيق أكواد الأخطاء (docs/errors/) من فهرس المترجم وأمثلة الاختبارات.

كل صفحة تحتوي: الشرح، مثالًا حقيقيًا يسبب الخطأ (من tests/corpus)، رسالة المترجم الفعلية
(من ملف .المتوقع)، والإصلاح مع مثال مصحَّح. الأمثلة المصححة تُشغَّل فعلًا أثناء التوليد،
فإن فشل أحدها يتوقف السكربت: التوثيق لا يمكن أن يخالف سلوك اللغة.

هذه الصفحات هي أيضًا مصدر المعرفة الذي يُغذّى به شارح الأخطاء الذكي (ai-explainer).

الاستخدام: python3 tools/gen_error_docs.py [--check]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "target" / "debug" / "dhad"
OUT = ROOT / "docs" / "errors"

RANGES = [
    (1, 999, "أخطاء التحليل اللغوي والنحوي", "تُكتشف قبل التشغيل: صياغة البرنامج نفسها غير صحيحة."),
    (1000, 1999, "أخطاء دلالية وأنواع", "الصياغة سليمة لكن المعنى غير صالح: اسم غير معرَّف، نوع غير مناسب…"),
    (2000, 2999, "أخطاء وقت التشغيل", "تظهر أثناء تنفيذ البرنامج بقيم معيّنة."),
    (3000, 3999, "تحذيرات المدقق", "لا توقف البرنامج، لكنها تشير غالبًا إلى خطأ أو التباس."),
    (4000, 4999, "قيود مولّد WebAssembly", "تظهر فقط عند الترجمة بـ «ضاد ترجم»؛ المفسر يشغّل البرنامج عادةً."),
]

# أمثلة تُسبب الخطأ لأكواد لا تغطيها tests/corpus، وأمثلة مصححة لكل كود.
EXTRA_BAD = {
    6: "دع س = ١٢أ",
    1011: "اطبع(صحيح + ١)",
    1012: "٥ = ٣",
    2005: "دع س = ٠\nطالما صحيح {\n    س = س + ١\n}",
    2007: "اطبع(طول(١٢٣))",
    3001: "دع غير_مستخدم = ٥\nاطبع(\"مرحبا\")",
    3002: "دع أسماء = [\"ليلى\"]\nدع اسماء = [\"سارة\"]\nاطبع(أسماء، اسماء)",
    3003: "دع عَدَد = ٣\nاطبع(عدد)",
    4001: "دع ق = [١، ٢، ٣]\nاطبع(ق)",
    4002: "دع س = ١\nس = صحيح\nاطبع(س)",
}

FIXES = {
    1: "دع س = ١٢",
    2: "اطبع((١ + ٢))",
    3: 'اطبع("نص مغلق")',
    4: "دع عدد١ = ١\nاطبع(عدد١)",
    5: "دع مدة = ١\nاطبع(مدة)",
    6: "دع س = ١٢\nاطبع(س)",
    1001: "دع المجموع = ١٠\nاطبع(المجموع)",
    1002: "دع ط = ٣\nط = ٤\nاطبع(ط)",
    1003: 'اطبع("العمر: " + نص(٢٥))\nاطبع("العمر: ${٢٥}")',
    1004: "دالة ف(أ) { أرجع أ }\nاطبع(ف(١))",
    1005: "دالة س() { أرجع ٥ }\nاطبع(س())",
    1006: "دالة واحد() {\n    أرجع ١\n}\nاطبع(واحد())",
    1007: "لكل ع في ١..١٠ {\n    إذا ع == ٣ { توقف }\n    اطبع(ع)\n}",
    1008: 'اطبع(١ < عدد("٢"))',
    1009: "استورد رياضيات\nاطبع(رياضيات.جذر(٩))",
    1010: 'دع س = ١\nإذا س != ٠ { اطبع("غير صفر") }',
    1011: "اطبع(١ + ١)",
    1012: "دع س = ٣\nس = ٥\nاطبع(س)",
    2001: 'دع ب = ٠\nإذا ب != ٠ { اطبع(١٠ / ب) } وإلا { اطبع("لا يمكن القسمة على صفر") }',
    2002: "دع ق = [١، ٢]\nاطبع(ق[طول(ق) - ١])",
    2003: 'دع ق = {"أ": ١}\nإذا "ب" في ق { اطبع(ق["ب"]) } وإلا { اطبع("المفتاح غير موجود") }',
    2004: "دالة عد_تنازلي(ن) {\n    إذا ن == ٠ { أرجع ٠ }\n    أرجع عد_تنازلي(ن - ١)\n}\nاطبع(عد_تنازلي(١٠))",
    2005: "دع س = ٠\nطالما س < ١٠ {\n    س = س + ١\n}\nاطبع(س)",
    2006: "تأكد(١ + ١ == ٢، \"الحساب سليم\")\nاطبع(\"نجح التأكيد\")",
    2007: 'اطبع(طول("١٢٣"))',
    2008: 'اطبع(عدد("٤٢") + ١)',
    3001: 'اطبع("مرحبا")',
    3002: 'دع أسماء = ["ليلى"، "سارة"]\nاطبع(أسماء)',
    3003: "دع عدد = ٣\nاطبع(عدد)",
    4001: "دع مجموع = ٠\nلكل ع في ١..٤ { مجموع = مجموع + ع }\nاطبع(مجموع)",
    4002: "دع س = ١\nس = ٢\nاطبع(س)",
}


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([str(CLI), *args], capture_output=True, text=True, input=stdin, cwd=ROOT)


def with_file(src: str, *args: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "مثال.ضاد"
        f.write_text(src + "\n", encoding="utf-8")
        return subprocess.run([str(CLI), *args, "مثال.ضاد"], capture_output=True, text=True, cwd=d)


def message_for(code: int, src: str) -> str:
    """رسالة المترجم الفعلية لمثال الخطأ."""
    if 3000 <= code < 4000:
        r = with_file(src, "افحص")
    elif code >= 4000:
        r = with_file(src, "ترجم", "--wat")
    else:
        r = with_file(src, "شغّل", "--وقود", "100000")
    text = r.stderr.strip()
    blocks = [b for b in text.split("\n\n") if f"ضاد-{code:04d}" in b.split("\n")[0]]
    return blocks[0].strip() if blocks else text


def verify_fix(code: int, src: str) -> str:
    """يتحقق أن المثال المصحح يعمل بلا أخطاء ولا يكرر الكود نفسه؛ يعيد مخرجاته."""
    if code >= 4000:
        r = with_file(src, "ترجم", "--wat")
        ok = r.returncode == 0
        out = "(تُرجم إلى WebAssembly بنجاح)"
    else:
        r = with_file(src, "شغّل")
        ok = r.returncode == 0
        out = r.stdout.strip()
        chk = with_file(src, "افحص")
        if f"ضاد-{code:04d}" in chk.stderr:
            ok = False
    if not ok:
        sys.exit(f"✘ المثال المصحح للكود {code} لا يعمل:\n{src}\n{r.stderr}")
    return out


def main() -> None:
    check = "--check" in sys.argv
    if not CLI.exists():
        subprocess.run(["cargo", "build", "-q", "-p", "dhad-cli"], cwd=ROOT, check=True)
    catalog = json.loads(run("فهرس").stdout)
    OUT.mkdir(parents=True, exist_ok=True)
    pages: dict[str, str] = {}

    for e in catalog:
        code = e["code"]
        cs = f"{code:04d}"
        corpus = ROOT / "tests" / "corpus" / f"خطأ_{cs}.ضاد"
        bad = corpus.read_text(encoding="utf-8").strip() if corpus.exists() else EXTRA_BAD.get(code)
        fix = FIXES.get(code)
        if bad is None or fix is None:
            sys.exit(f"✘ الكود {code} بلا مثال خاطئ أو مصحح")
        msg = message_for(code, bad)
        if f"ضاد-{cs}" not in msg:
            sys.exit(f"✘ المثال الخاطئ للكود {code} لا يُنتج هذا الكود:\n{bad}\n{msg}")
        fixed_out = verify_fix(code, fix)
        related = [x for x in catalog if x["code"] != code and x["code"] // 1000 == code // 1000][:4]
        rng = next(r for r in RANGES if r[0] <= code <= r[1])
        md = [
            f"# ضاد-{cs}: {e['title']}",
            "",
            f"> الفئة: **{rng[2]}** — {rng[3]}",
            "",
            "## ماذا يعني؟",
            "",
            e["explanation"],
            "",
            "## مثال يسبب الخطأ",
            "",
            "```dhad",
            bad,
            "```",
            "",
            "رسالة المترجم:",
            "",
            "```text",
            msg,
            "```",
            "",
            "## كيف أصلحه؟",
            "",
            e["help"],
            "",
            "```dhad",
            fix,
            "```",
            "",
        ]
        if fixed_out:
            md += ["المخرجات بعد الإصلاح:", "", "```text", fixed_out, "```", ""]
        if related:
            md += ["## أخطاء ذات صلة", ""]
            md += [f"- [ضاد-{r['code']:04d}]({r['code']:04d}.md): {r['title']}" for r in related]
            md.append("")
        md += ["---", "", f"اعرض هذه الصفحة من الطرفية: `ضاد شرح {code}`", ""]
        pages[f"{cs}.md"] = "\n".join(md)

    index = ["# فهرس أكواد أخطاء ضاد", "",
             "كل خطأ يصدره المترجم يحمل كودًا بصيغة `ضاد-XXXX` وصفحة هنا تشرح سببه وإصلاحه بمثال يعمل فعلًا.",
             "هذه الصفحات مولَّدة آليًا بـ `tools/gen_error_docs.py`، وأمثلتها المصححة تُشغَّل عند كل توليد.", ""]
    for lo, hi, name, desc in RANGES:
        entries = [e for e in catalog if lo <= e["code"] <= hi]
        if not entries:
            continue
        index += [f"## {name} ({lo:04d}–{hi:04d})", "", desc, "", "| الكود | العنوان |", "|---|---|"]
        index += [f"| [ضاد-{e['code']:04d}]({e['code']:04d}.md) | {e['title']} |" for e in entries]
        index.append("")
    pages["README.md"] = "\n".join(index)

    stale = []
    for name, content in pages.items():
        path = OUT / name
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(name)
        else:
            path.write_text(content, encoding="utf-8")
    if check and stale:
        sys.exit(f"✘ صفحات قديمة (شغّل tools/gen_error_docs.py): {', '.join(stale)}")
    print(f"✔ {len(pages) - 1} صفحة خطأ + الفهرس {'محدَّثة' if check else 'كُتبت في docs/errors'}")


if __name__ == "__main__":
    main()
