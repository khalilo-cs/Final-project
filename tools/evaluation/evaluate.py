"""Compare the system's suggested grades with the committee's, for the thesis chapter.

    python -m tools.evaluation.evaluate --url http://localhost:8080 --course <id> \\
        --user dr.ali --faculty-grades committee.csv --out results.html

committee.csv (UTF-8): `student_number` or `project_id`, `faculty_grade`, and optionally
`authored` (yes/no) for the comprehension-fingerprint pilot. Without the file, the grades
professors approved inside the system are used (see the report's warning about that).
"""

import argparse
import csv
import getpass
import html
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from tools.evaluation.stats import DEFAULT_BANDS, Agreement, agreement, auc, mean


@dataclass
class Row:
    project_id: str
    student_number: str | None
    title: str
    system: float | None
    coverage: float
    in_system_final: float | None
    faculty: float | None = None
    authored: bool | None = None
    fingerprint: float | None = None


@dataclass
class Report:
    course_id: str
    source: str  # "blind" (committee file) or "in_system"
    agreement: Agreement | None
    rows: list[Row]
    skipped: list[str] = field(default_factory=list)
    fingerprint: dict | None = None
    bands: list[tuple[float, str]] = field(default_factory=lambda: list(DEFAULT_BANDS))


# -- fetching -----------------------------------------------------------------------------


class Api:
    def __init__(self, base: str, transport: httpx.BaseTransport | None = None) -> None:
        self.http = httpx.Client(base_url=base.rstrip("/"), timeout=60, transport=transport)

    def login(self, user: str, password: str) -> None:
        response = self.http.post("/svc/auth/api/v1/auth/login",
                                  json={"username": user, "password": password})  # fmt: skip
        response.raise_for_status()
        self.http.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    def get(self, path: str) -> dict:
        response = self.http.get(f"/svc/projects{path}")
        response.raise_for_status()
        return response.json()

    def rows(self, course_id: str, with_fingerprint: bool) -> list[Row]:
        data = self.get(f"/api/v1/grades/course/{course_id}")
        rows = []
        for item in data["projects"]:
            row = Row(project_id=item["project_id"], student_number=item.get("student_number"),
                      title=item["title"], system=item["suggested_total"],
                      coverage=item["coverage"], in_system_final=item["final_total"])  # fmt: skip
            if with_fingerprint:
                try:
                    row.fingerprint = self.get(f"/api/v1/fingerprint/{row.project_id}")["score"]
                except httpx.HTTPStatusError:
                    row.fingerprint = None
            rows.append(row)
        return rows


# -- joining ------------------------------------------------------------------------------


def _number(value: str) -> float | None:
    value = (value or "").strip().replace("٫", ".")
    value = value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    try:
        return float(value)
    except ValueError:
        return None


def read_committee(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as source:  # Excel adds a BOM
        return list(csv.DictReader(source))


def join(rows: list[Row], committee: list[dict] | None) -> tuple[list[Row], list[str]]:
    """Attach the faculty grade to each project; returns (rows, problems)."""
    problems: list[str] = []
    if committee is None:
        for row in rows:
            row.faculty = row.in_system_final
        return rows, problems
    by_id = {r.project_id: r for r in rows}
    by_number = {r.student_number: r for r in rows if r.student_number}
    for line_no, entry in enumerate(committee, start=2):
        key_id = (entry.get("project_id") or "").strip()
        key_number = (entry.get("student_number") or "").strip()
        row = by_id.get(key_id) or by_number.get(key_number)
        if row is None:
            problems.append(
                f"السطر {line_no}: لا يوجد مشروع بالمعرّف/الرقم «{key_id or key_number}»"
            )
            continue
        grade = _number(entry.get("faculty_grade", ""))
        if grade is None or not 0 <= grade <= 100:
            problems.append(f"السطر {line_no}: درجة غير صالحة «{entry.get('faculty_grade')}»")
            continue
        row.faculty = grade
        flag = (entry.get("authored") or "").strip().lower()
        if flag in ("yes", "y", "1", "true", "نعم"):
            row.authored = True
        elif flag in ("no", "n", "0", "false", "لا"):
            row.authored = False
    return rows, problems


def build(course_id: str, rows: list[Row], committee: list[dict] | None,
          bands: list[tuple[float, str]] = DEFAULT_BANDS) -> Report:  # fmt: skip
    rows, problems = join(rows, committee)
    paired = [r for r in rows if r.system is not None and r.faculty is not None]
    for r in rows:
        if r not in paired:
            reason = "لا درجة مقترحة" if r.system is None else "لا درجة لجنة"
            problems.append(f"«{r.title}»: {reason}")
    result = (agreement([r.system for r in paired], [r.faculty for r in paired], bands)
              if len(paired) >= 2 else None)  # fmt: skip
    fingerprint = None
    authors = [r.fingerprint for r in rows if r.authored is True and r.fingerprint is not None]
    others = [r.fingerprint for r in rows if r.authored is False and r.fingerprint is not None]
    if authors or others:
        fingerprint = {
            "authors": len(authors), "others": len(others),
            "mean_authors": mean(authors) if authors else None,
            "mean_others": mean(others) if others else None,
            "auc": auc(authors, others),
        }  # fmt: skip
    return Report(course_id, "blind" if committee is not None else "in_system", result, rows,
                  problems, fingerprint, list(bands))  # fmt: skip


# -- rendering ----------------------------------------------------------------------------

_BLUE = "#2a78d6"


def _fmt(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _ci(interval: tuple[float, float] | None, digits: int = 2) -> str:
    return (
        ""
        if interval is None
        else f" <span class=ci><bdi dir=ltr>[{interval[0]:.{digits}f} – {interval[1]:.{digits}f}]</bdi></span>"
    )


def _scatter(rows: list[Row]) -> str:
    """Faculty grade (x) against the system's (y); points on the diagonal agree."""
    size, pad = 360, 40
    span = size - 2 * pad

    def at(v: float) -> float:
        return pad + v / 100 * span

    grid = "".join(
        f'<line x1="{at(t)}" y1="{pad}" x2="{at(t)}" y2="{size - pad}" class=grid />'
        f'<line x1="{pad}" y1="{size - at(t)}" x2="{size - pad}" y2="{size - at(t)}" class=grid />'
        f'<text x="{at(t)}" y="{size - pad + 16}" text-anchor=middle>{t}</text>'
        f'<text x="{pad - 8}" y="{size - at(t) + 4}" text-anchor=end>{t}</text>'
        for t in range(0, 101, 20)
    )
    points = "".join(
        f'<circle cx="{at(r.faculty):.1f}" cy="{size - at(r.system):.1f}" r="5" fill="{_BLUE}" '
        f'stroke="#fff" stroke-width="2"><title>{html.escape(r.title)}: اللجنة {r.faculty:g}، '
        f"النظام {r.system:g}</title></circle>"
        for r in rows if r.system is not None and r.faculty is not None
    )  # fmt: skip
    return (
        f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="درجة النظام مقابل درجة اللجنة" '
        f"class=chart dir=ltr>{grid}"
        f'<line x1="{at(0)}" y1="{size - at(0)}" x2="{at(100)}" y2="{size - at(100)}" '
        f'class=diag /><text x="{at(96)}" y="{size - at(100) - 6}" text-anchor=end class=note>'
        f"تطابق تام</text>{points}"
        f'<text x="{size / 2}" y="{size - 6}" text-anchor=middle class=axis>درجة اللجنة</text>'
        f'<text x="12" y="{size / 2}" text-anchor=middle class=axis '
        f'transform="rotate(-90 12 {size / 2})">درجة النظام</text></svg>'
    )


def render(report: Report) -> str:
    a = report.agreement
    rows = [r for r in report.rows if r.system is not None and r.faculty is not None]
    warn = ""
    if report.source == "in_system":
        warn = ("<p class=warn>هذه الدرجات اعتمدها الدكاترة <b>داخل النظام بعد رؤية الدرجة "
                "المقترحة</b>، فقد تكون متأثرة بها. للنتائج المنشورة استخدم درجات تضعها اللجنة "
                "دون رؤية النظام (ملف CSV).</p>")  # fmt: skip
    cards = ""
    body = "<p>لا توجد مشاريع كافية بدرجتين للمقارنة (يلزم مشروعان على الأقل).</p>"
    if a is not None:
        cards = "".join(
            f"<div class=card><div class=v><bdi dir=ltr>{v}</bdi></div><div class=k>{k}</div></div>"
            for k, v in [
                ("عدد المشاريع", a.n),
                ("متوسط الفرق المطلق", f"{a.mae:.1f}{_ci(a.mae_ci, 1)}"),
                ("ارتباط بيرسون", f"{_fmt(a.pearson)}{_ci(a.pearson_ci)}"),
                ("كابا الموزونة (التقديرات)", _fmt(a.kappa)),
                ("ضمن ±10 درجات", f"{a.within_10:.0%}"),
                ("الانحياز (النظام − اللجنة)", f"{a.bias:+.1f}"),
            ]
        )
        labels = [label for _, label in report.bands]
        head = "".join(f"<th>{html.escape(x)}</th>" for x in labels)
        matrix = "".join(
            f"<tr><th>{html.escape(labels[i])}</th>"
            + "".join(f"<td class={'hit' if i == j else ''}>{n or ''}</td>" for j, n in enumerate(line))
            + "</tr>"
            for i, line in enumerate(a.confusion)
        )  # fmt: skip
        worst = sorted(rows, key=lambda r: abs(r.system - r.faculty), reverse=True)[:5]
        worst_rows = "".join(
            f"<tr><td>{html.escape(r.title)}</td><td>{r.faculty:g}</td><td>{r.system:g}</td>"
            f"<td><bdi dir=ltr>{r.system - r.faculty:+.1f}</bdi></td><td>{r.coverage:g}%</td></tr>"
            for r in worst
        )
        body = f"""
<div class=grid2>
  <figure>{_scatter(rows)}<figcaption>كل نقطة مشروع؛ النقاط فوق الخط قيّمها النظام أعلى من اللجنة.</figcaption></figure>
  <div>
    <h3>تطابق التقديرات</h3>
    <table class=matrix><tr><th>اللجنة ↓ / النظام →</th>{head}</tr>{matrix}</table>
    <p class=small>الخانات الملونة تطابق في التقدير: {a.exact_band:.0%} من المشاريع.</p>
    <p class=small>حدود الاتفاق (Bland-Altman، 95%): من <bdi dir=ltr>{a.limits[0]:+.1f}</bdi> إلى <bdi dir=ltr>{a.limits[1]:+.1f}</bdi> درجة.</p>
  </div>
</div>
<h3>أكبر الفروق (تستحق المراجعة)</h3>
<table><tr><th>المشروع</th><th>اللجنة</th><th>النظام</th><th>الفرق</th><th>التغطية</th></tr>{worst_rows}</table>
<p class=small>«التغطية» نسبة معايير التقييم التي توفرت لها بيانات (مثلاً بلا مناقشة = أقل من 100%)؛ الفروق الكبيرة مع تغطية منخفضة متوقعة.</p>"""
    fp = ""
    if report.fingerprint:
        f = report.fingerprint
        fp = f"""
<h2>تجربة بصمة الفهم</h2>
<table><tr><th></th><th>العدد</th><th>متوسط الدرجة</th></tr>
<tr><td>أصحاب الكود</td><td>{f["authors"]}</td><td>{_fmt(f["mean_authors"], 1)}</td></tr>
<tr><td>متطوعون على كود غيرهم</td><td>{f["others"]}</td><td>{_fmt(f["mean_others"], 1)}</td></tr></table>
<p><b>AUC = {_fmt(f["auc"])}</b>: احتمال أن يحصل صاحب كود عشوائي على درجة أعلى من متطوع عشوائي
(0.5 = لا تمييز، 1 = تمييز تام).</p>
<p class=small>العينات الصغيرة تعطي أرقاماً غير مستقرة؛ اذكر العدد مع النتيجة دائماً.</p>"""
    problems = ""
    if report.skipped:
        items = "".join(f"<li>{html.escape(p)}</li>" for p in report.skipped)
        problems = f"<h3>ملاحظات على البيانات</h3><ul class=small>{items}</ul>"
    return f"""<!doctype html><html lang=ar dir=rtl><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>نتائج تقييم النظام</title>
<style>
:root {{ --fg:#1a1a1a; --muted:#55555a; --line:#d8d8de; --bg:#fcfcfb; --card:#f3f4f8; --blue:{_BLUE}; }}
body {{ font-family: "Noto Naskh Arabic","Noto Sans Arabic","DejaVu Sans",sans-serif; color:var(--fg);
  background:var(--bg); max-width:980px; margin:0 auto; padding:24px 16px; line-height:1.8; }}
h1 {{ font-size:22px; }} h2 {{ font-size:18px; margin-top:28px; }} h3 {{ font-size:15px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }}
.card {{ background:var(--card); border-radius:10px; padding:10px; text-align:center; }}
.card .v {{ font-size:20px; font-weight:bold; }} .card .k {{ font-size:12px; color:var(--muted); }}
.ci {{ font-size:11px; color:var(--muted); font-weight:normal; display:block; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; align-items:start; }}
@media (max-width:700px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
.chart {{ width:100%; max-width:380px; font-size:11px; fill:var(--muted); }}
.chart .grid {{ stroke:var(--line); stroke-width:1; }} .chart .diag {{ stroke:#8a8a90; stroke-dasharray:4 4; }}
.chart .axis {{ font-size:12px; fill:var(--fg); }}
table {{ border-collapse:collapse; width:100%; font-size:13px; margin:8px 0; }}
th, td {{ border:1px solid var(--line); padding:4px 8px; text-align:center; }} th {{ background:var(--card); }}
.matrix td.hit {{ background:#dbe8f8; font-weight:bold; }}
.small {{ font-size:12px; color:var(--muted); }}
.warn {{ background:#fff4e0; border-right:4px solid #eda100; padding:8px 12px; }}
figcaption {{ font-size:12px; color:var(--muted); }}
</style></head><body>
<h1>نتائج تقييم فاحص المشاريع الذكي</h1>
<p class=small>المادة {html.escape(report.course_id)} — مقارنة الدرجة المقترحة بدرجة {"اللجنة (تقييم أعمى)" if report.source == "blind" else "الدكتور داخل النظام"}. الأرقام بين القوسين فترات ثقة 95% (bootstrap).</p>
{warn}<div class=cards>{cards}</div>{body}{fp}{problems}
<h2>كيف تُقرأ هذه الأرقام</h2>
<ul class=small>
<li><b>متوسط الفرق المطلق:</b> كم درجة يبتعد النظام عن اللجنة في المتوسط.</li>
<li><b>ارتباط بيرسون:</b> هل يرتّب النظام المشاريع كما ترتبها اللجنة (1 = تماماً).</li>
<li><b>كابا الموزونة:</b> الاتفاق على التقدير (ممتاز/جيد جداً/…) بعد استبعاد ما يحدث صدفة؛ الخطأ بتقديرين أسوأ من الخطأ بتقدير واحد. 0.6–0.8 جيد، وفوق 0.8 ممتاز.</li>
<li><b>الانحياز:</b> موجب = النظام أكرم من اللجنة، سالب = أشد.</li>
</ul>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url", default="http://localhost:8080", help="the web interface (nginx gateway)"
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--user", required=True, help="a faculty or admin account")
    parser.add_argument("--faculty-grades", type=Path, help="committee CSV (blind grades)")
    parser.add_argument(
        "--bands",
        help='JSON, e.g. [[90,"ممتاز"],[80,"جيد جداً"],[65,"جيد"],[50,"مقبول"],[0,"ضعيف"]]',
    )
    parser.add_argument("--out", type=Path, default=Path("evaluation-results.html"))
    parser.add_argument("--json", type=Path, help="also save the raw numbers")
    args = parser.parse_args(argv)

    bands = [tuple(b) for b in json.loads(args.bands)] if args.bands else DEFAULT_BANDS
    committee = read_committee(args.faculty_grades) if args.faculty_grades else None
    wants_fingerprint = bool(committee) and any(e.get("authored") for e in committee)
    api = Api(args.url)
    api.login(args.user, getpass.getpass(f"كلمة مرور {args.user}: "))
    report = build(args.course, api.rows(args.course, wants_fingerprint), committee, bands)
    args.out.write_text(render(report), encoding="utf-8")
    if args.json:
        args.json.write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    a = report.agreement
    if a:
        print(
            f"n={a.n}  MAE={a.mae:.1f}  r={_fmt(a.pearson)}  kappa={_fmt(a.kappa)}  bias={a.bias:+.1f}"
        )
    for problem in report.skipped:
        print("!", problem, file=sys.stderr)
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
