"""وثيقة المشروع بالمكونات المطلوبة من المشرفة، في نسختين من محتوى واحد:
PDF للطباعة و Word (docx) للتعديل.

    python docs/project-document/build.py
"""

from pathlib import Path

HERE = Path(__file__).parent
TITLE = "مِحَكّ"
SUBTITLE = "نظام ذكي لتقييم المشاريع البرمجية في كل مستويات الحاسوب والتحقق من فهم الطالب لها وأصالتها"
FILL = "........................................"

# Each block: ("h", text) heading, ("p", text) paragraph, ("ul", [items]) list,
# ("table", [header], [rows]) table, ("note", text) highlighted paragraph.
SECTIONS: list[tuple[str, list]] = [
    ("1. البيانات التعريفية", [
        ("table", ["البند", "البيان"], [
            ["اسم المشروع", "مِحَكّ (Mihakk)"],
            ["العنوان الكامل", SUBTITLE],
            ["نوع المشروع", "مشروع تخرج — بكالوريوس"],
            ["مجال المشروع", "هندسة البرمجيات، والذكاء الاصطناعي في التعليم، وأمن المعلومات"],
            ["الجامعة / الكلية", "جامعة صنعاء — كلية الحاسوب وتكنولوجيا المعلومات"],
            ["القسم", FILL],
            ["إعداد الطالب", "المهندس محمد عبدالرحيم خليل"],
            ["الرقم الجامعي", FILL],
            ["المشرف/ة", FILL],
            ["العام الجامعي", FILL],
            ["المدة المتوقعة", "فصلان دراسيان (قرابة 32 أسبوعاً)"],
            ["نوع المخرَج", "نظام ويب يعمل على خادم الكلية، مع وثائق المشروع ودليل المستخدم"],
        ]),
    ]),
    ("2. المشكلة", [
        ("p", "تستقبل كلية الحاسوب كل فصل مئات الأعمال البرمجية: واجبات أسبوعية في السنوات الأولى، "
              "ومشاريع مواد، ومشاريع تخرج. ويعتمد تقييمها كلياً على وقت عضو هيئة التدريس وخبرته، "
              "فتظهر المشكلات الآتية:"),
        ("ul", [
            "<b>ضيق الوقت مقابل كثرة الأعمال:</b> فحص مشروع تخرج واحد بدقة يأخذ ساعات، ومراجعة "
            "واجبات مئات الطلاب أسبوعياً شبه مستحيلة يدوياً، فيُقيَّم كثير منها بنظرة سريعة.",
            "<b>تفاوت التقييم:</b> تختلف المعايير من ممتحن لآخر، ولا يحصل الطالب غالباً على ملاحظات "
            "مفصلة يتعلم منها.",
            "<b>صعوبة التحقق من أصالة العمل:</b> تُنسخ الأعمال بين الطلاب أو من دفعات سابقة، ويكفي "
            "تغيير أسماء المتغيرات لخداع المقارنة اليدوية.",
            "<b>الكود المولَّد بالذكاء الاصطناعي:</b> صار الطالب قادراً على تقديم مشروع يعمل دون أن "
            "يفهمه، وأدوات كشف التشابه التقليدية لا تكشف ذلك لأن الكود جديد وليس منسوخاً.",
            "<b>جوانب لا تُفحص منهجياً:</b> أمان الكود، وتصميم قاعدة البيانات، وأداء البرنامج، "
            "وتطابق التقرير مع ما في الكود فعلاً.",
            "<b>الظروف المحلية:</b> انقطاع الكهرباء وضعف الإنترنت يقطعان الرفع والمناقشة الإلكترونية، "
            "والأدوات العالمية مدفوعة بالدولار وضعيفة مع اللغة العربية، وإرسال أعمال الطلاب إلى "
            "خوادم خارجية يمس خصوصيتهم.",
        ]),
        ("note", "<b>صياغة المشكلة:</b> كيف يمكن تقييم الأعمال البرمجية للطلاب في كل المستويات "
                 "تقييماً سريعاً وموحداً وعادلاً، مع التحقق من أن الطالب كتب عمله ويفهمه، في ظل "
                 "قلة وقت الدكاترة وضعف البنية التحتية؟"),
    ]),
    ("3. الهدف", [
        ("h", "الهدف العام"),
        ("p", "بناء نظام يساعد عضو هيئة التدريس على تقييم الأعمال البرمجية للطلاب بسرعة وعدالة، "
              "ويتحقق من فهم الطالب لعمله وأصالته، ويقترح درجة مبررة يبقى قرارها النهائي للدكتور."),
        ("h", "الأهداف التفصيلية"),
        ("ul", [
            "تحليل الكود آلياً: الجودة والتعقيد والتصميم والثغرات الأمنية، بست لغات برمجة.",
            "تحليل قاعدة البيانات (المفاتيح والتطبيع) والتقرير (الانتحال ومطابقته للكود).",
            "إجراء مناقشة ذكية مع الطالب أسئلتها من كوده هو، كتابةً أو بالصوت، تتكيف مع مستواه.",
            "التحقق من أصالة العمل بأدلة متعددة، منها اختبار «بصمة الفهم» على كود الطالب نفسه.",
            "اقتراح درجة مفصلة مع سبب كل جزء، وتقارير PDF و Excel للدكتور وإحصائيات للقسم.",
            "العمل في ظروفنا: على خادم الكلية بلا إنترنت، ومقاوماً لانقطاع الكهرباء، وبالعربية.",
        ]),
    ]),
    ("4. الأهمية", [
        ("table", ["الجانب", "وجه الأهمية"], [
            ["لعضو هيئة التدريس", "توفير مئات الساعات كل فصل، ومعايير موحدة، وأدلة جاهزة عند الشك في الغش."],
            ["للطالب", "ملاحظات مفصلة يتعلم منها فوراً، وتقييم عادل لا يتأثر بمن يقيّمه، وإنصاف "
                       "صاحب العمل الأصلي."],
            ["للكلية والقسم", "رفع جودة المخرجات، وإحصائيات عن الأخطاء الشائعة تفيد في تطوير "
                              "المناهج، ودعم متطلبات الجودة والاعتماد الأكاديمي."],
            ["علمياً", "يجمع تحليل الكود والذكاء الاصطناعي وكشف الغش في منظومة واحدة، ويقدم فكرة "
                       "جديدة هي «بصمة الفهم»: التحقق من فهم الطالب لا من تشابه كوده فقط."],
            ["محلياً", "حل يعمل بلا اشتراكات ولا إنترنت، يصمد أمام انقطاع الكهرباء، يحافظ على "
                       "خصوصية الطلاب، ويدعم العربية، ويمكن تعميمه على الجامعات اليمنية."],
        ]),
    ]),
    ("5. النطاق", [
        ("h", "5.1 النطاق الوظيفي"),
        ("p", "<b>يشمل النظام:</b>"),
        ("ul", [
            "إدارة المستخدمين بثلاثة أدوار: طالب، ودكتور، ومدير نظام، مع الدخول بحساب الجامعة.",
            "إدارة المواد وتسجيل الطلاب فيها، وتحديد مستوى المادة ونوع العمل (واجب، مشروع مادة، مشروع تخرج).",
            "تسليم المشروع: كود (ملف ZIP أو رابط Git) وتقرير (PDF أو Word) وقاعدة بيانات.",
            "التحليل الآلي: الكود، والأمان، وقاعدة البيانات، والتقرير، والأداء.",
            "المناقشة الذكية وبصمة الفهم، وكشف الغش وتقدير أصالة المشروع.",
            "الدرجة المقترحة والتقارير والإحصائيات، وتعلم النظام من تصحيحات الدكاترة.",
        ]),
        ("p", "<b>لا يشمل النظام:</b>"),
        ("ul", [
            "إعطاء الدرجة النهائية آلياً: النظام يقترح، والدكتور يقرر دائماً.",
            "اتهام الطالب بالغش: النظام يعرض قرائن على الدكتور وحده، ولا يراها الطالب.",
            "تقييم المشاريع غير البرمجية، أو قراءة المخططات المرسومة كصور داخل التقرير.",
            "الربط بنظام الدرجات الرسمي للجامعة (يمكن إضافته لاحقاً).",
        ]),
        ("h", "5.2 النطاق المكاني"),
        ("ul", [
            "<b>مكان التطبيق الأول:</b> كلية الحاسوب وتكنولوجيا المعلومات — جامعة صنعاء، بأقسامها، "
            "ولكل المستويات من السنة الأولى حتى الدراسات العليا.",
            "<b>مكان التشغيل:</b> خادم داخل الكلية على شبكة الجامعة، ويُستخدم من أي جهاز أو جوال "
            "عبر المتصفح داخل الحرم، ومن خارجه إن أتاحت الجامعة ذلك.",
            "<b>إمكانية التوسع:</b> كليات وأقسام أخرى تُدرِّس البرمجة، ثم الجامعات اليمنية الحكومية "
            "والأهلية، فالنظام يعمل دون إنترنت ودون اشتراكات.",
        ]),
    ]),
    ("6. المعنيون بالأمر", [
        ("p", "الجهات التي تتأثر بالمشروع أو تؤثر فيه، ودور كل منها:"),
        ("table", ["الجهة", "الدور", "التأثير", "الدرجة"], [
            ["الطلاب", "يسلّمون أعمالهم، ويجرون المناقشة واختبار بصمة الفهم، ويستلمون الملاحظات.",
             "المستفيد الأول: ملاحظات أوضح وتقييم أعدل. ونجاح النظام يتوقف على تقبّلهم له.", "عالية"],
            ["الدكاترة والممتحنون", "ينشئون المواد ويحددون الأوزان، ويراجعون النتائج، ويعتمدون الدرجات.",
             "يوفر وقتهم ويوحد معاييرهم. وتصحيحاتهم هي ما يتعلم منه النظام ويحسّن دقته.", "عالية"],
            ["المشرف/ة على المشروع", "توجيه العمل ومراجعة مراحله واعتماده.",
             "يحدد اتجاه المشروع ويضمن جودته العلمية.", "عالية"],
            ["رئيس القسم", "متابعة إحصائيات القسم، واعتماد استخدام النظام في المواد.",
             "صاحب قرار التطبيق، ويستفيد من البيانات في تطوير المناهج.", "متوسطة إلى عالية"],
            ["عمادة الكلية وإدارة الجامعة", "الموافقة على تبني النظام، وتوفير الخادم والموارد.",
             "قرار التعميم والتمويل بيدها، وتستفيد في الجودة والاعتماد الأكاديمي.", "عالية"],
            ["مدير النظام (فني الكلية)", "تشغيل النظام وتحديثه، وإدارة الحسابات والنسخ الاحتياطي.",
             "استمرار عمل النظام يعتمد عليه.", "متوسطة"],
            ["مركز تقنية المعلومات بالجامعة", "ربط النظام بحسابات الجامعة وشبكتها.",
             "يسهّل الدخول الموحد والوصول من الحرم.", "متوسطة"],
            ["لجان الجودة والاعتماد الأكاديمي", "الاطلاع على تقارير التقييم وإحصائياته.",
             "تستفيد من التوثيق المنظم لأعمال الطلاب ونتائجها.", "منخفضة إلى متوسطة"],
            ["سوق العمل وجهات التوظيف", "مستفيد غير مباشر.",
             "خريجون يفهمون ما يبرمجون ويكتبون كوداً آمناً.", "منخفضة (غير مباشرة)"],
        ]),
    ]),
    ("7. لمحة عن التطبيق", [
        ("p", "نظام ويب عربي يعمل على خادم الكلية، ويتكون من خدمات مستقلة (Microservices). "
              "رحلة العمل فيه باختصار:"),
        ("ol", [
            "ينشئ الدكتور المادة ويحدد مستواها ونوع العمل.",
            "يرفع الطالب مشروعه، ويُستكمل الرفع تلقائياً إذا انقطع الاتصال.",
            "يحلل النظام الكود والأمان وقاعدة البيانات والتقرير والأداء، ويقارن المشروع بغيره.",
            "يجري الطالب مناقشة ذكية واختبار «بصمة الفهم» على كوده.",
            "يقترح النظام درجة مفصلة مع أسبابها، ويعتمدها الدكتور أو يعدّلها.",
        ]),
        ("p", "<b>التقنيات:</b> Python و FastAPI للخدمات، و React للواجهة، و PostgreSQL لقاعدة البيانات، "
              "و Docker للتشغيل، ونماذج ذكاء اصطناعي تعمل محلياً."),
    ]),
]


# ---------------------------------------------------------------- HTML -> PDF

CSS = """
@page { size: A4; margin: 2cm 1.9cm;
        @bottom-center { content: counter(page); font-size: 9pt; color: #666; } }
@page :first { @bottom-center { content: ""; } }
body { font-family: "DejaVu Sans", sans-serif; font-size: 11pt; line-height: 1.85; color: #1a1a1a; }
h1 { font-size: 15pt; color: #2b3a8f; border-bottom: 2px solid #2b3a8f; padding-bottom: 3px;
     margin: 22px 0 8px; break-after: avoid; }
h2 { font-size: 12pt; color: #2b3a8f; margin: 12px 0 4px; break-after: avoid; }
p { margin: 5px 0; text-align: justify; }
ul, ol { margin: 4px 0; padding-right: 22px; }
li { margin: 3px 0; text-align: justify; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 10pt; }
th { background: #2b3a8f; color: #fff; padding: 5px 8px; text-align: right; }
td { border: 1px solid #c9cde0; padding: 5px 8px; vertical-align: top; }
tr { break-inside: avoid; }
tr:nth-child(even) td { background: #f5f6fb; }
td:first-child { font-weight: bold; white-space: nowrap; }
.note { border: 1px solid #c9cde0; border-right: 5px solid #2b3a8f; background: #f5f6fb;
        padding: 7px 12px; margin: 10px 0; }
.cover { text-align: center; padding-top: 2.5cm; break-after: page; }
.cover .uni { font-size: 14pt; line-height: 2; }
.cover .title { font-size: 30pt; font-weight: bold; color: #2b3a8f; margin-top: 2.2cm; }
.cover .en { font-size: 14pt; color: #555; }
.cover .sub { font-size: 13pt; margin-top: 12px; }
.cover .doc { display: inline-block; margin-top: 22px; padding: 6px 26px; border: 2px solid #2b3a8f;
              border-radius: 6px; font-size: 14pt; font-weight: bold; color: #2b3a8f; }
.cover table { width: 72%; margin: 2.2cm auto 0; font-size: 12pt; }
.cover td { border: none; background: none !important; padding: 6px; }
.cover td:first-child { color: #555; font-weight: normal; width: 35%; }
"""


def html() -> str:
    parts = [f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>وثيقة المشروع — {TITLE}</title><style>{CSS}</style></head><body>
<div class="cover">
  <div class="uni">الجمهورية اليمنية<br>جامعة صنعاء<br>كلية الحاسوب وتكنولوجيا المعلومات</div>
  <div class="title">{TITLE}</div><div class="en">Mihakk</div>
  <div class="sub">{SUBTITLE}</div>
  <div class="doc">وثيقة المشروع</div>
  <table>
    <tr><td>إعداد</td><td><b>المهندس محمد عبدالرحيم خليل</b></td></tr>
    <tr><td>الرقم الجامعي</td><td>{FILL}</td></tr>
    <tr><td>إشراف</td><td>{FILL}</td></tr>
    <tr><td>العام الجامعي</td><td>{FILL}</td></tr>
  </table>
</div>"""]
    for heading, blocks in SECTIONS:
        # The stakeholders table is long: start it on a fresh page.
        page = ' style="break-before: page"' if heading.startswith("6.") else ""
        parts.append(f"<h1{page}>{heading}</h1>")
        for block in blocks:
            kind = block[0]
            if kind == "h":
                parts.append(f"<h2>{block[1]}</h2>")
            elif kind == "p":
                parts.append(f"<p>{block[1]}</p>")
            elif kind == "note":
                parts.append(f'<p class="note">{block[1]}</p>')
            elif kind in ("ul", "ol"):
                items = "".join(f"<li>{item}</li>" for item in block[1])
                parts.append(f"<{kind}>{items}</{kind}>")
            elif kind == "table":
                head = "".join(f"<th>{h}</th>" for h in block[1])
                rows = "".join(
                    "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in block[2]
                )
                parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
    parts.append("</body></html>")
    return "\n".join(parts)


# ---------------------------------------------------------------- Word (docx)


def docx(path: Path) -> None:
    import re

    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    blue = RGBColor(0x2B, 0x3A, 0x8F)
    doc = Document()
    for section in doc.sections:
        section.right_margin = section.left_margin = Pt(54)
        # Right-to-left page: tables and columns start from the right.
        section._sectPr.append(OxmlElement("w:bidi"))

    def rtl(paragraph, align=WD_ALIGN_PARAGRAPH.RIGHT):
        paragraph.alignment = align
        p_pr = paragraph._p.get_or_add_pPr()
        p_pr.append(OxmlElement("w:bidi"))
        return paragraph

    def run(paragraph, text, bold=False, size=12, color=None):
        r = paragraph.add_run(text)
        r.bold = bold
        r.font.size = Pt(size)
        r.font.name = "Arial"
        r_pr = r._r.get_or_add_rPr()
        fonts = r_pr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            r_pr.append(fonts)
        fonts.set(qn("w:cs"), "Arial")
        r_pr.append(OxmlElement("w:rtl"))
        size_cs = OxmlElement("w:szCs")
        size_cs.set(qn("w:val"), str(size * 2))
        r_pr.append(size_cs)
        if bold:
            r_pr.append(OxmlElement("w:bCs"))
        if color is not None:
            r.font.color.rgb = color
        return r

    def rich(paragraph, html_text, size=12):
        """<b>..</b> inside the text becomes bold runs."""
        for i, piece in enumerate(re.split(r"</?b>", html_text)):
            if piece:
                run(paragraph, piece, bold=i % 2 == 1, size=size)

    def shade(cell, fill):
        tc_pr = cell._tc.get_or_add_tcPr()
        shading = OxmlElement("w:shd")
        shading.set(qn("w:val"), "clear")
        shading.set(qn("w:fill"), fill)
        tc_pr.append(shading)

    # Cover page.
    for line, size, bold in [("الجمهورية اليمنية", 14, False), ("جامعة صنعاء", 14, False),
                             ("كلية الحاسوب وتكنولوجيا المعلومات", 14, False)]:  # fmt: skip
        run(rtl(doc.add_paragraph(), WD_ALIGN_PARAGRAPH.CENTER), line, bold, size)
    for _ in range(4):
        doc.add_paragraph()
    run(rtl(doc.add_paragraph(), WD_ALIGN_PARAGRAPH.CENTER), TITLE, True, 32, blue)
    run(rtl(doc.add_paragraph(), WD_ALIGN_PARAGRAPH.CENTER), "Mihakk", False, 14)
    run(rtl(doc.add_paragraph(), WD_ALIGN_PARAGRAPH.CENTER), SUBTITLE, False, 13)
    doc.add_paragraph()
    run(rtl(doc.add_paragraph(), WD_ALIGN_PARAGRAPH.CENTER), "وثيقة المشروع", True, 16, blue)
    for _ in range(3):
        doc.add_paragraph()
    for label, value in [("إعداد", "المهندس محمد عبدالرحيم خليل"), ("الرقم الجامعي", FILL),
                         ("إشراف", FILL), ("العام الجامعي", FILL)]:  # fmt: skip
        p = rtl(doc.add_paragraph(), WD_ALIGN_PARAGRAPH.CENTER)
        run(p, f"{label}: ", False, 13)
        run(p, value, True, 13)
    doc.add_page_break()

    for heading, blocks in SECTIONS:
        run(rtl(doc.add_paragraph()), heading, True, 16, blue)
        for block in blocks:
            kind = block[0]
            if kind == "h":
                run(rtl(doc.add_paragraph()), block[1], True, 13, blue)
            elif kind in ("p", "note"):
                p = rtl(doc.add_paragraph(), WD_ALIGN_PARAGRAPH.JUSTIFY)
                rich(p, block[1])
            elif kind in ("ul", "ol"):
                for n, item in enumerate(block[1], start=1):
                    p = rtl(doc.add_paragraph(), WD_ALIGN_PARAGRAPH.JUSTIFY)
                    p.paragraph_format.right_indent = Pt(14)
                    rich(p, f"{n}. " if kind == "ol" else "• ")
                    rich(p, item)
            elif kind == "table":
                header, rows = block[1], block[2]
                table = doc.add_table(rows=1, cols=len(header))
                table.style = "Table Grid"
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                tbl_pr = table._tbl.tblPr
                tbl_pr.append(OxmlElement("w:bidiVisual"))
                for cell, text in zip(table.rows[0].cells, header, strict=True):
                    shade(cell, "2B3A8F")
                    p = rtl(cell.paragraphs[0])
                    run(p, text, True, 11, RGBColor(0xFF, 0xFF, 0xFF))
                for row in rows:
                    cells = table.add_row().cells
                    for i, (cell, text) in enumerate(zip(cells, row, strict=True)):
                        p = rtl(cell.paragraphs[0])
                        run(p, text, bold=i == 0, size=11)
                widths = {2: [4.2, 12.3], 4: [3.6, 5.0, 5.4, 2.5]}.get(len(header))
                for row in table.rows:
                    for i, cell in enumerate(row.cells):
                        if widths:
                            cell.width = Cm(widths[i])
                        for paragraph in cell.paragraphs:
                            paragraph.paragraph_format.space_before = Pt(3)
                            paragraph.paragraph_format.space_after = Pt(3)
                margins = OxmlElement("w:tblCellMar")
                for side in ("top", "bottom", "start", "end", "left", "right"):
                    margin = OxmlElement(f"w:{side}")
                    margin.set(qn("w:w"), "80" if side in ("top", "bottom") else "110")
                    margin.set(qn("w:type"), "dxa")
                    margins.append(margin)
                tbl_pr.append(margins)
                doc.add_paragraph()
    doc.save(path)


if __name__ == "__main__":
    from weasyprint import HTML

    (HERE / "project-document.html").write_text(html(), encoding="utf-8")
    HTML(string=html(), base_url=str(HERE)).write_pdf(HERE / "project-document.pdf")
    docx(HERE / "project-document.docx")
    print("written:", *(p.name for p in sorted(HERE.glob("project-document.*"))))
