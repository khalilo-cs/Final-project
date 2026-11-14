"""Course grade sheet as .xlsx (FR-10.5)."""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.services.grading import CRITERIA, LABELS_AR

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")


def _safe(value):
    """Stop spreadsheet formula injection from user-provided text (titles, notes)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def grade_sheet(course_name: str, weights: dict[str, float], rows: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "الدرجات"
    sheet.sheet_view.rightToLeft = True

    headers = ["الرقم الجامعي", "اسم الطالب", "عنوان المشروع", "الحالة"]
    headers += [f"{LABELS_AR[c]} ({weights[c]:g}%)" for c in CRITERIA]
    headers += ["الدرجة المقترحة", "نسبة التغطية %", "الدرجة النهائية", "ملاحظات الدكتور"]
    sheet.append([f"كشف درجات: {_safe(course_name)}"])
    sheet.append(headers)
    for cell in sheet[2]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row in rows:
        sheet.append(
            [
                _safe(row.get("student_number")),
                _safe(row.get("student_name")),
                _safe(row["title"]),
                row["status"],
                *[row["scores"].get(c) for c in CRITERIA],
                row["suggested_total"],
                row["coverage"],
                row["final_total"],
                _safe(row.get("faculty_notes")),
            ]
        )

    sheet["A1"].font = Font(bold=True, size=14)
    for index, header in enumerate(headers, 1):
        sheet.column_dimensions[get_column_letter(index)].width = max(12, min(40, len(header) + 4))
    sheet.freeze_panes = "A3"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
