import json

from app.analyzers.consistency import check_consistency
from app.analyzers.plagiarism import check_and_index, remove_document
from app.parsers.extract import extract
from app.services.report_service import analyze_report
from tests.conftest import make_docx, make_pdf, token

ORIGINAL_AR = (
    "يهدف هذا المشروع إلى بناء نظام متكامل لإدارة المكتبة الجامعية يتيح للطلاب البحث عن "
    "الكتب واستعارتها إلكترونياً ويتيح لأمين المكتبة متابعة الإعارات المتأخرة وإرسال "
    "التنبيهات للطلاب بشكل تلقائي عبر البريد الإلكتروني مع توفير تقارير شهرية عن حركة الكتب"
)
OTHER_AR = (
    "يتناول هذا البحث تصميم تطبيق للهاتف المحمول يساعد المزارعين في اليمن على معرفة "
    "مواعيد الري المناسبة لكل محصول اعتماداً على بيانات الطقس اليومية وطبيعة التربة "
    "ويعرض نصائح مبسطة باللغة العربية مع إمكانية العمل دون اتصال بالإنترنت"
)
FILLER = [
    f"الفقرة رقم {i} تشرح جانباً مختلفاً من جوانب العمل باستخدام مصطلحات خاصة {i}x{i}"
    for i in range(30)
]


def report(*paragraphs):
    return make_docx([("مقدمة", list(paragraphs))])


def run(db, doc_id, data, filename="r.docx", facts=None, index=True):
    return analyze_report(db, doc_id, data, filename, facts, index)


# ---- extraction ----------------------------------------------------------------------


def test_extract_docx_headings_and_tables():
    import io

    from docx import Document

    document = Document()
    document.add_heading("الفصل الأول: المقدمة", level=1)
    document.add_paragraph("نص الفقرة")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "users", "جدول المستخدمين"
    buffer = io.BytesIO()
    document.save(buffer)

    extracted = extract(buffer.getvalue(), "Report.DOCX")
    assert extracted.format == "docx" and extracted.tables == 1
    assert [(p.text, p.is_heading) for p in extracted.paragraphs] == [
        ("الفصل الأول: المقدمة", True),
        ("نص الفقرة", False),
        ("users | جدول المستخدمين", False),
    ]


def test_extract_pdf():
    extracted = extract(make_pdf(["1. Introduction", "This system manages a library."]), "r.pdf")
    assert extracted.pages == 1
    assert [p.text for p in extracted.paragraphs] == [
        "1. Introduction",
        "This system manages a library.",
    ]


def test_extract_rejects_bad_files():
    import pytest

    from app.parsers.extract import ExtractionError

    for data, name in [(b"junk", "a.pdf"), (b"junk", "a.docx"), (b"x", "a.txt")]:
        with pytest.raises(ExtractionError):
            extract(data, name)


# ---- plagiarism ----------------------------------------------------------------------


def test_copied_passage_is_found_with_its_source(db):
    first = run(db, "p1", report(ORIGINAL_AR, *FILLER[:5]))
    assert first["plagiarism"]["plagiarism_percentage"] == 0.0
    assert first["plagiarism"]["corpus_size"] == 0

    # Copy with different diacritics/hamza spelling: still detected after normalization.
    respelled = ORIGINAL_AR.replace("إلى", "الى").replace("إلكترونياً", "الكترونيا")
    second = run(db, "p2", report(OTHER_AR, respelled, *FILLER[10:12]))
    plagiarism = second["plagiarism"]
    assert [s["document_id"] for s in plagiarism["sources"]] == ["p1"]
    assert 20 < plagiarism["plagiarism_percentage"] < 80
    top = plagiarism["passages"][0]
    assert top["source"] == "p1" and top["words"] >= 20
    assert "المكتبة الجامعية" in top["text"]  # excerpt is the original spelling


def test_unrelated_reports_do_not_match(db):
    run(db, "p1", report(ORIGINAL_AR, *FILLER[:3]))
    result = run(db, "p2", report(OTHER_AR))
    assert result["plagiarism"]["sources"] == []
    assert result["plagiarism"]["plagiarism_percentage"] == 0.0


def test_reanalysis_replaces_own_entry(db):
    data = report(ORIGINAL_AR, *FILLER[:5])
    run(db, "p1", data)
    again = run(db, "p1", data)  # must not match itself
    assert again["plagiarism"]["sources"] == [] and again["plagiarism"]["corpus_size"] == 0


def test_boilerplate_shared_by_many_reports_is_ignored(db):
    header = "جامعة صنعاء كلية الحاسوب وتكنولوجيا المعلومات قسم علوم الحاسوب مشروع تخرج مقدم لنيل درجة البكالوريوس"
    for i in range(6):
        run(db, f"old{i}", report(header, FILLER[i * 4], FILLER[i * 4 + 1]))
    result = run(db, "new", report(header, OTHER_AR))
    assert result["plagiarism"]["ignored_boilerplate"] > 0
    assert result["plagiarism"]["sources"] == []


def test_index_false_and_removal(db):
    run(db, "p1", report(ORIGINAL_AR), index=False)
    assert run(db, "p2", report(ORIGINAL_AR))["plagiarism"]["sources"] == []
    assert run(db, "p3", report(ORIGINAL_AR))["plagiarism"]["sources"][0]["document_id"] == "p2"
    assert remove_document(db, "p2") is True
    assert remove_document(db, "p2") is False
    assert check_and_index(db, "p4", ORIGINAL_AR, index=False).sources[0]["document_id"] == "p3"


# ---- consistency ---------------------------------------------------------------------

FACTS = {
    "languages": {"Java": 10, "SQL": 1},
    "technologies": ["Spring Boot", "MySQL", "JDBC"],
    "architecture": [],
    "total_tables": 4,
}


def types(result):
    return sorted((i["type"], i["severity"]) for i in result["inconsistencies"])


def test_report_matches_code():
    text = "تم بناء النظام بلغة جافا باستخدام Spring Boot وقاعدة بيانات MySQL تحتوي على 4 جداول"
    result = check_consistency(text, FACTS)
    assert result["mentioned_technologies"] == {"Java": 1, "Spring Boot": 1, "MySQL": 1}
    assert result["inconsistencies"] == []


def test_report_contradicts_code():
    text = (
        "استخدمنا React في الواجهة. واجهة React سريعة. مكونات React قابلة لإعادة الاستخدام. "
        "تم استخدام نمط MVC. قاعدة البيانات تتكون من ١٠ جداول. "
        "اطلعنا أيضاً على Django في الدراسات السابقة."
    )
    assert types(check_consistency(text, FACTS)) == [
        ("architecture_mismatch", "Low"),
        ("claimed_not_found", "Low"),  # Django: one mention (literature review)
        ("claimed_not_found", "Medium"),  # React: repeated claim
        ("table_count_mismatch", "Medium"),
        ("undocumented", "Low"),  # MySQL used but never mentioned
        ("undocumented", "Low"),  # Spring Boot
    ]


def test_javascript_is_not_java():
    result = check_consistency("The frontend is written in JavaScript (Node.js).", FACTS)
    assert "Java" not in result["mentioned_technologies"]
    assert "JavaScript" in result["mentioned_technologies"]


def test_no_facts_means_no_consistency_check():
    result = check_consistency("We used React.", None)
    assert result["checked"] is False and result["inconsistencies"] == []


# ---- documentation -------------------------------------------------------------------


def test_documentation_quality(db):
    complete = make_docx(
        [
            ("الفصل الأول: مقدمة", ["نص"] * 3),
            ("1.2 مشكلة البحث", ["نص"]),
            ("1.3 الأهداف", ["نص"]),
            ("الفصل الثاني: الدراسات السابقة", ["نص"]),
            ("المتطلبات", ["نص"]),
            ("الفصل الثالث: تصميم النظام", ["شكل (1): مخطط الحالات", "جدول 2 المستخدمون"]),
            ("التنفيذ", ["نص"]),
            ("الاختبار", ["نص"]),
            ("الخاتمة", ["نص"]),
            ("المراجع", [f"[{i}] Author, Title, Journal, 2021." for i in range(1, 13)]),
        ]
    )
    result = run(db, "full", complete)["documentation"]
    assert result["sections_missing"] == []
    assert result["references_count"] == 12
    assert result["figure_and_table_captions"] == 2

    partial = run(db, "partial", make_docx([("Introduction", ["Some text."])]))["documentation"]
    assert partial["sections_found"] == ["introduction"]
    assert partial["documentation_quality_score"] < result["documentation_quality_score"]


def test_scanned_report_warning(db):
    result = run(db, "img", make_pdf(["Title only"]), filename="scan.pdf")
    assert result["warnings"] and "scanned" in result["warnings"][0]


# ---- API -----------------------------------------------------------------------------


def post(client, data, auth=None, filename="report.docx", **form):
    return client.post(
        "/api/v1/analysis/report",
        files={"file": (filename, data)},
        data={"document_id": "proj-1", **form},
        headers={"Authorization": f"Bearer {auth or token()}"},
    )


def test_api_only_for_service(client):
    data = report(ORIGINAL_AR)
    assert post(client, data, auth=token(role="admin")).status_code == 403
    assert post(client, data, auth=token(token_type="refresh")).status_code == 401
    assert (
        client.delete(
            "/api/v1/documents/x", headers={"Authorization": f"Bearer {token('student')}"}
        ).status_code
        == 403
    )


def test_api_analyze_and_forget(client):
    body = post(client, report(ORIGINAL_AR), facts=json.dumps(FACTS)).json()
    assert body["format"] == "docx" and body["consistency"]["checked"] is True
    assert 0 <= body["overall_report_score"] <= 100
    assert post(client, b"not a docx").status_code == 400
    assert post(client, report("x"), facts="[1]").status_code == 422
    assert post(client, report("x"), document_id="../etc").status_code == 422
    auth = {"Authorization": f"Bearer {token()}"}
    assert client.delete("/api/v1/documents/proj-1", headers=auth).status_code == 204


def test_dotnet_report_consistency():
    facts = {
        "languages": {"C#": 8},
        "technologies": ["SQL Server", "Windows Forms", "ASP.NET Core"],
        "architecture": [],
    }
    text = (
        "تم تطوير النظام بلغة سي شارب باستخدام Windows Forms وقاعدة بيانات SQL Server. "
        "ولوحة الويب مبنية بـ ASP.NET. واستخدمنا Qt في نسخة سابقة."
    )
    result = check_consistency(text, facts)
    assert {"C#", "Windows Forms", "SQL Server", "ASP.NET"} <= set(result["mentioned_technologies"])
    assert [(i["type"], i["report_claim"]) for i in result["inconsistencies"]] == [
        ("claimed_not_found", "The report mentions Qt (1 times)"),
        ("undocumented", "The report never mentions ASP.NET Core"),
    ]


# ---- database description and UML (FR-05.7, FR-06.5) ------------------------------------


def test_report_tables_missing_from_schema():
    facts = {**FACTS, "tables": ["users", "orders"]}
    text = (
        "The users table stores accounts. The orders table stores purchases. "
        "We also keep a payments table for invoices, and جدول coupons للخصومات."
    )
    found = [i for i in check_consistency(text, facts)["inconsistencies"]
             if i["type"] == "table_not_in_schema"]  # fmt: skip
    assert sorted(i["report_claim"].split("'")[1] for i in found) == ["coupons", "payments"]


def test_uml_class_diagram_checked_against_code():
    facts = {**FACTS, "classes": ["User", "OrderService", "Product"]}
    text = (
        "Figure 4: Class Diagram. The class User is linked to OrderService and to "
        "PaymentGateway. InvoicePrinter prints receipts. We used JavaScript and MySQL."
    )
    result = check_consistency(text, facts)
    uml = result["uml"]
    assert uml["has_uml"] and "class" in uml["diagrams"]
    assert uml["classes_matched"] == ["OrderService", "User"]
    assert uml["classes_not_in_code"] == ["InvoicePrinter", "PaymentGateway"]
    assert uml["code_classes_documented_pct"] == 66.7
    assert "uml_class_not_found" in [i["type"] for i in result["inconsistencies"]]


def test_no_uml_section_reports_nothing():
    result = check_consistency("A simple report with no diagrams.", {**FACTS, "classes": ["A"]})
    assert result["uml"] == {"has_uml": False, "diagrams": []}
