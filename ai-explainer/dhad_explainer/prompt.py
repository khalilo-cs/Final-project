"""بناء الموجّه. موجّه النظام ثابت تمامًا (يُخزَّن مؤقتًا)، وكل ما يتغير في رسالة المستخدم."""
from __future__ import annotations

from .knowledge import reference_text
from .levels import LEVELS

RULES = """أنت مساعد تعليمي يشرح أخطاء البرمجة بلغة «ضاد» العربية لطلاب مبتدئين.
المترجم اكتشف الخطأ بالفعل وحدد كوده وسطره؛ مهمتك الشرح فقط.

قواعد صارمة:
١. اعتمد فقط على صفحة الخطأ المعني في «مرجع أخطاء ضاد» أدناه وعلى كود الطالب. لا تضف معلومات من خارجهما، ولا تخترع دوالًا أو كلمات مفتاحية غير موجودة في المرجع.
٢. التزم بالمستوى المطلوب وحده، ولا تكشف أكثر منه.
٣. اكتب بعربية فصحى بسيطة وجمل قصيرة، وخاطب الطالب مباشرة بلطف.
٤. إن ذكرت سطرًا فاذكر السطر المعطى فقط. لا تذكر أي كود خطأ غير الكود المعطى.
٥. كتل الكود تُكتب بالصيغة ```dhad ... ``` وبلغة ضاد فقط، وفقط إن سمح المستوى بها.
٦. لا تكتب مقدمات ولا خاتمة؛ ابدأ بالشرح مباشرة.

## مرجع أخطاء ضاد
"""


def system_prompt() -> str:
    return RULES + "\n" + reference_text()


def numbered_snippet(source: str, line: int, radius: int = 3) -> str:
    lines = source.split("\n")
    lo, hi = max(1, line - radius), min(len(lines), line + radius)
    width = len(str(hi))
    out = []
    for n in range(lo, hi + 1):
        marker = "→" if n == line else " "
        out.append(f"{marker} {str(n).rjust(width)} │ {lines[n - 1]}")
    return "\n".join(out)


def user_message(error: dict, source: str, level: int) -> str:
    lv = LEVELS[level]
    line = error.get("line") or 1
    return "\n".join([
        f"الخطأ: {error['codeStr']} — {error['message']}",
        f"السطر: {line}",
        "",
        "كود الطالب (السهم يشير إلى سطر الخطأ):",
        "```dhad",
        numbered_snippet(source, line),
        "```",
        "",
        f"المستوى المطلوب: {lv.number} — {lv.title}",
        f"التعليمات: {lv.instruction}",
        f"الحد الأقصى: {lv.max_words} كلمة خارج كتل الكود.",
    ])
