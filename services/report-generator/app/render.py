"""HTML -> PDF with WeasyPrint. Student-provided text is escaped by Jinja2 autoescape."""

from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import get_settings

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


class BlockedResource(Exception):
    pass


def _no_external_resources(url: str, *args, **kwargs):
    """The PDF engine may not fetch anything (no SSRF, no file:// reads)."""
    raise BlockedResource(url)


def _bar_chart(breakdown: list[dict], audience: str) -> str:
    rows = [b for b in breakdown if b.get("score") is not None]
    if audience != "staff":
        rows = [b for b in rows if b["criterion"] != "authenticity"]
    if not rows:
        return ""
    width, bar, gap = 500, 16, 8
    height = len(rows) * (bar + gap)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}" style="direction:ltr">']  # fmt: skip
    for i, row in enumerate(rows):
        y = i * (bar + gap)
        score = max(0.0, min(100.0, float(row["score"])))
        color = "#059669" if score >= 75 else "#d97706" if score >= 50 else "#e11d48"
        length = score / 100 * 330
        parts.append(f'<rect x="0" y="{y}" width="330" height="{bar}" fill="#f1f5f9" rx="3"/>')
        parts.append(f'<rect x="{330 - length:.1f}" y="{y}" width="{length:.1f}" height="{bar}" '
                     f'fill="{color}" rx="3"/>')  # fmt: skip
        parts.append(f'<text x="{340}" y="{y + 12}" font-size="10" fill="#334155" '
                     f'font-family="DejaVu Sans">{int(round(score))}</text>')  # fmt: skip
    parts.append("</svg>")
    labels = "".join(
        f'<div style="height:{bar + gap}px;line-height:{bar}px">{_escape(r["label_ar"])}</div>'
        for r in rows
    )
    return (f'<div style="display:flex;gap:8px;align-items:flex-start;margin:6px 0">'
            f'<div style="width:120px;font-size:9pt">{labels}</div>{"".join(parts)}</div>')  # fmt: skip


def _escape(text: str) -> str:
    from markupsafe import escape

    return str(escape(text))


def render_html(data: dict) -> str:
    audience = data.get("audience", "student")
    grade = data.get("grade") or {"breakdown": [], "coverage": 0}
    context = {
        **data,
        "audience": audience,
        "grade": grade,
        "university": get_settings().university,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "chart": _bar_chart(grade.get("breakdown", []), audience),
    }
    return _env.get_template("student_report.html").render(**context)


def render_pdf(data: dict) -> bytes:
    from weasyprint import HTML

    return HTML(string=render_html(data), url_fetcher=_no_external_resources).write_pdf()
