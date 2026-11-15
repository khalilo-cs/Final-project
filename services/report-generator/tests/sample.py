GRADE = {
    "suggested_total": 78.4, "coverage": 100.0, "final_total": None, "faculty_notes": None,
    "breakdown": [
        {"criterion": "code_quality", "label_ar": "جودة الكود", "weight": 20, "score": 95.0, "justification": "4 files, 120 lines"},
        {"criterion": "security", "label_ar": "الأمان", "weight": 10, "score": 75.0, "justification": "1 critical (SQL Injection)"},
        {"criterion": "database", "label_ar": "قاعدة البيانات", "weight": 10, "score": 80.0, "justification": "2 tables, 3NF"},
        {"criterion": "report", "label_ar": "التقرير", "weight": 15, "score": 61.5, "justification": "plagiarism 4%"},
        {"criterion": "viva", "label_ar": "المناقشة", "weight": 25, "score": 70.0, "justification": "viva 70"},
        {"criterion": "authenticity", "label_ar": "أصالة المشروع", "weight": 10, "score": 34.6, "justification": "98% similar"},
        {"criterion": "performance", "label_ar": "الأداء", "weight": 10, "score": 90.0, "justification": "p95 120 ms"},
    ],
}  # fmt: skip
REPORT = {
    "project": {"title": "نظام إدارة المكتبة <script>alert(1)</script>"},
    "student": {"name": "سارة علي", "number": "2022123"},
    "course": "CS499 - مشروع التخرج",
    "grade": GRADE,
    "advice": {"summary": None,
               "strengths": [{"title": "كود نظيف ومنظم", "evidence": "درجة 95"}],
               "weaknesses": [{"title": "SQL Injection (1)", "evidence": "app.py:6"}],
               "improvements": [{"title": "استخدم الاستعلامات المُعدّة", "evidence": "app.py:6", "priority": "high"}]},
    "code": {"total_files": 4, "total_lines": 120, "total_classes": 1, "total_functions": 6,
             "cyclomatic_complexity_avg": 3.2, "details": {"stack": {"technologies": [{"name": "Flask"}]},
             "most_complex_functions": [{"function": "calculate_fine", "file": "app.py", "line": 12, "cyclomatic_complexity": 5}]}},
    "security": {"vulnerabilities": [{"severity": "Critical", "type": "SQL Injection", "file": "app.py", "line": 6, "description": "string formatting"}]},
    "performance": {"status": "done", "runs_successfully": True, "error": None,
                    "details": {"startup_seconds": 2.1, "memory_peak_mb": 120, "load_test": [{"concurrent_users": 50, "p50_ms": 40, "p95_ms": 120, "error_rate": 0}]}},
    "authenticity": {"authenticity_score": 34.6, "coverage": 90, "flags": [{"severity": "High", "evidence": "98% of the code matches a project submitted earlier"}]},
}  # fmt: skip
