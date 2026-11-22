"""Strengths, weaknesses and what to improve, each with its evidence.

Built from the analysis results with fixed rules, so it works without any language
model; viva-engine can then rewrite it as a short readable summary.
"""

from collections import Counter

from app.services.grading import ProjectResults

_SMELL_AR = {
    "long_method": "دوال طويلة",
    "too_many_parameters": "دوال بمعاملات كثيرة",
    "high_complexity": "دوال عالية التعقيد",
    "deep_nesting": "تداخل عميق للشروط",
    "god_class": "كلاسات ضخمة تقوم بكل شيء",
    "duplicate_code": "كود مكرر (نسخ ولصق)",
    "dead_code": "دوال أو كلاسات غير مستخدمة",
    "n_plus_one_query": "استعلامات داخل حلقات (N+1)",
}
_FIX_AR = {
    "SQL Injection": "استخدم الاستعلامات المُعدّة (parameterized) بدل دمج المدخلات في نص SQL",
    "Command Injection": "مرّر الأوامر كقائمة معاملات ولا تستخدم shell مع مدخلات المستخدم",
    "Cross-Site Scripting (XSS)": "رمّز (encode) أي مدخلات قبل عرضها في الصفحة",
    "Path Traversal": "تحقق أن المسار النهائي يبقى داخل مجلد الرفع",
    "Hardcoded Secret": "انقل كلمات المرور والمفاتيح إلى متغيرات البيئة",
    "Insecure Deserialization": "لا تفك تسلسل بيانات غير موثوقة؛ استخدم JSON",
    "Weak Hash Algorithm": "استخدم bcrypt أو argon2 لكلمات المرور",
    "CSRF": "فعّل حماية CSRF وأرسل رمز التحقق (token) مع كل نموذج يغيّر البيانات",
    "Missing Input Validation": "تحقق من نوع المدخلات وطولها وصيغتها قبل استخدامها",
}
_DB_AR = {
    "missing_primary_key": "جداول بلا مفتاح أساسي",
    "missing_foreign_key": "علاقات بلا مفتاح أجنبي",
    "repeating_group": "أعمدة مكررة تخالف 1NF",
    "multivalued_column": "عدة قيم في حقل واحد (تخالف 1NF)",
    "partial_dependency": "اعتماد جزئي على المفتاح (يخالف 2NF)",
    "transitive_dependency": "نسخ بيانات من جدول آخر (يخالف 3NF)",
    "plaintext_password": "كلمات مرور مخزنة كنص واضح",
    "float_for_money": "FLOAT للمبالغ المالية",
    "date_as_text": "تواريخ مخزنة كنص",
}
_SECTION_AR = {
    "introduction": "المقدمة", "problem_statement": "مشكلة البحث", "objectives": "الأهداف",
    "literature_review": "الدراسات السابقة", "requirements": "المتطلبات",
    "design": "التصميم", "implementation": "التنفيذ", "testing": "الاختبار",
    "conclusion": "الخاتمة", "references": "المراجع",
}  # fmt: skip


def _item(category, title, evidence, priority=None):
    entry = {"category": category, "title": title, "evidence": evidence}
    if priority:
        entry["priority"] = priority
    return entry


def build_advice(results: ProjectResults) -> dict:
    strengths, weaknesses, improvements = [], [], []
    code, security, database, report = (
        results.code,
        results.security,
        results.database,
        results.report,
    )

    if code:
        stack = code.stack or {}
        if stack.get("architecture"):
            strengths.append(_item("code", f"بنية منظمة ({', '.join(stack['architecture'])})",
                                   "فصل واضح بين طبقات المشروع في المجلدات"))  # fmt: skip
        if code.overall_quality_score >= 80:
            strengths.append(_item("code", "كود نظيف ومنظم",
                                   f"درجة الجودة {code.overall_quality_score}/100، متوسط التعقيد "
                                   f"{code.cyclomatic_complexity_avg}"))  # fmt: skip
        graph = code.details.get("graph") or {}
        if patterns := graph.get("design_patterns"):
            names = list(dict.fromkeys(p["name_ar"] for p in patterns))[:4]
            strengths.append(_item("code", "استخدام أنماط تصميم: " + "، ".join(names),
                                   "؛ ".join(p["evidence_ar"] for p in patterns[:3])))  # fmt: skip
        for cycle in graph.get("dependencies", {}).get("file_cycles", [])[:2]:
            improvements.append(_item("code", "اكسر الاعتماد الدائري بين الملفات: انقل الجزء "
                                      "المشترك إلى ملف ثالث يعتمد عليه الاثنان",
                                      " ← ".join([*cycle, cycle[0]]), "medium"))  # fmt: skip
        for issue in (graph.get("solid") or {}).get("issues", []):
            if issue["severity"] == "Medium":
                improvements.append(_item("code", f"مبدأ {issue['principle']}: "
                                          f"{issue['evidence_ar']}",
                                          f"{issue.get('file') or ''}:{issue.get('line') or ''}",
                                          "low"))  # fmt: skip
        smells = Counter(s["type"] for s in code.code_smells)
        for kind, count in smells.most_common():
            examples = [s["symbol"] for s in code.code_smells if s["type"] == kind][:3]
            weaknesses.append(_item("code", f"{_SMELL_AR.get(kind, kind)} ({count})",
                                    "مثل: " + "، ".join(examples)))  # fmt: skip
        if smells.get("duplicate_code"):
            percent = code.details.get("code_duplication_percentage", 0)
            improvements.append(_item("code", "انقل الكود المكرر إلى دالة مشتركة واحدة؛ أي إصلاح "
                                      "لاحق يصبح في مكان واحد", f"{percent}% من الأسطر مكررة",
                                      "medium"))  # fmt: skip
        if smells.get("dead_code"):
            names = [d["name"] for d in code.details.get("dead_code", [])[:4]]
            improvements.append(_item("code", "راجع الدوال غير المستخدمة واحذفها إن لم تكن "
                                      "تُستدعى من مكان لا يراه التحليل (قالب أو سكربت)",
                                      "، ".join(names), "low"))  # fmt: skip
        # Length/complexity advice only for those findings, not for copies or unused code.
        classic = sum(n for k, n in smells.items() if k not in ("duplicate_code", "dead_code"))
        if classic:
            improvements.append(_item("code", "قسّم الدوال الطويلة والمعقدة إلى دوال أصغر بأسماء "
                                      "واضحة؛ يسهّل الفهم والاختبار", f"{classic} ملاحظة جودة",
                                      "medium"))  # fmt: skip
        files = [f["path"].lower() for f in code.details.get("files", [])]
        if files and not any("test" in path for path in files):
            weaknesses.append(_item("code", "لا توجد اختبارات آلية",
                                    "لم يُعثر على ملفات اختبار في المشروع"))  # fmt: skip
            improvements.append(_item("code", "أضف اختبارات وحدة للوظائف الأساسية (pytest / "
                                      "JUnit)", "لا توجد ملفات test", "medium"))  # fmt: skip
        if code.details.get("parse_errors"):
            weaknesses.append(
                _item(
                    "code",
                    "ملفات بها أخطاء صياغة",
                    "، ".join(e["file"] for e in code.details["parse_errors"][:3]),
                )
            )

    if security:
        if not security.critical_count and not security.high_count:
            score = security.overall_security_score
            strengths.append(_item("security", "لا ثغرات أمنية خطيرة", f"درجة الأمان {score}/100"))
        by_type: dict[str, list] = {}
        for vulnerability in security.vulnerabilities:
            by_type.setdefault(vulnerability.get("type", "?"), []).append(vulnerability)
        for kind, found in by_type.items():
            places = "، ".join(f"{v.get('file', '?')}:{v.get('line', '?')}" for v in found[:3])
            severity = found[0].get("severity", "Medium")
            weaknesses.append(_item("security", f"{kind} ({len(found)})", places))
            if kind in _FIX_AR:
                priority = "high" if severity in ("Critical", "High") else "medium"
                improvements.append(_item("security", _FIX_AR[kind], places, priority))

    if database:
        counts = database.details.get("issue_counts", {})
        if database.total_tables and not counts:
            strengths.append(_item("database", "تصميم قاعدة بيانات سليم",
                                   f"{database.total_tables} جداول، "
                                   f"{database.normalization_level}"))  # fmt: skip
        for kind, count in counts.items():
            if kind in _DB_AR:
                weaknesses.append(
                    _item(
                        "database",
                        f"{_DB_AR[kind]} ({count})",
                        f"التطبيع المقدّر: {database.normalization_level}",
                    )
                )
        for issue in database.details.get("issues", [])[:5]:
            if issue.get("suggestion"):
                priority = "high" if issue.get("severity") == "High" else "low"
                improvements.append(
                    _item("database", issue.get("message", ""), issue["suggestion"], priority)
                )

    if report:
        documentation = report.details.get("documentation", {})
        if report.plagiarism_percentage < 5:
            strengths.append(_item("report", "تقرير أصيل", "لا تشابه يُذكر مع التقارير السابقة"))
        elif report.plagiarism_percentage >= 15:
            weaknesses.append(_item("report", f"تشابه {report.plagiarism_percentage}% مع تقارير "
                                    "أخرى", "راجع المقاطع المتشابهة واكتبها بأسلوبك مع ذكر "
                                    "المصدر"))  # fmt: skip
            improvements.append(_item("report", "أعد صياغة المقاطع المتشابهة ووثّق المصادر",
                                      f"{report.plagiarism_percentage}%", "high"))  # fmt: skip
        if report.documentation_quality_score >= 70:
            strengths.append(
                _item("report", "توثيق جيد", f"{report.documentation_quality_score}/100")
            )
        missing = documentation.get("sections_missing", [])
        if missing:
            names = "، ".join(_SECTION_AR.get(m, m) for m in missing)
            weaknesses.append(_item("report", "فصول ناقصة في التقرير", names))
            improvements.append(_item("report", f"أضف الفصول: {names}", "هيكل التقرير المتوقع",
                                      "medium"))  # fmt: skip
        for inconsistency in report.inconsistencies:
            if inconsistency.get("severity") == "Medium":
                weaknesses.append(_item("report", "تناقض بين التقرير والكود",
                                        f"{inconsistency.get('report_claim', '')} — "
                                        f"{inconsistency.get('code_reality', '')}"))  # fmt: skip

    performance = results.performance
    if performance and performance.status == "done":
        if not performance.runs_successfully:
            weaknesses.append(_item("performance", "المشروع لا يعمل عند تشغيله",
                                    performance.error or ""))  # fmt: skip
            # Nothing else matters much if the project does not run at all.
            improvements.append(_item("performance", "تأكد أن المشروع يعمل من نسخة نظيفة: أضف "
                                      "كل المكتبات إلى requirements.txt أو package.json",
                                      performance.error or "", "critical"))  # fmt: skip
        elif (performance.overall_performance_score or 0) >= 90:
            strengths.append(
                _item(
                    "performance",
                    "أداء جيد تحت الضغط",
                    f"درجة الأداء {performance.overall_performance_score}/100",
                )
            )
        for flag in performance.details.get("flags", []):
            if flag["type"] != "does_not_run":
                weaknesses.append(
                    _item("performance", flag.get("evidence_ar") or flag["type"], flag["evidence"])
                )

    order = {"critical": -1, "high": 0, "medium": 1, "low": 2}
    improvements.sort(key=lambda i: order.get(i.get("priority"), 3))
    return {"strengths": strengths, "weaknesses": weaknesses, "improvements": improvements}
