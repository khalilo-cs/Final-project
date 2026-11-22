"""The built-in engine: questions from project facts and rule-based answer grading.

It works with no language model at all, so the system is never dependent on one.
"""

import re

from app.providers.base import Evaluation, Provider, Question
from app.text.normalize import normalize, tokenize

# Key points a good answer about a vulnerability fix should mention.
_FIX_POINTS = {
    "SQL Injection": ["prepared", "parameter", "placeholder", "?", "معامل", "parameterized"],
    "Command Injection": ["shell", "escape", "whitelist", "list of arguments", "validate"],
    "Code Injection": ["eval", "literal_eval", "validate", "avoid"],
    "Cross-Site Scripting (XSS)": ["escape", "encode", "sanitize", "تشفير", "ترميز"],
    "Path Traversal": ["normalize", "base directory", "..", "whitelist", "canonical"],
    "Insecure Deserialization": ["json", "safe", "trusted", "whitelist"],
    "Hardcoded Secret": ["environment", "env", "متغير", "vault", "config"],
    "Weak Hash Algorithm": ["bcrypt", "argon2", "sha-256", "salt"],
    "CSRF": ["token", "samesite", "cookie", "csrf", "رمز"],
    "Missing Input Validation": ["validate", "type", "length", "schema", "whitelist", "تحقق"],
}
_VAGUE = [
    "تقريبا", "شي ما", "شيء ما", "بشكل عام", "مثل كذا", "وكذا", "something", "kind of",
    "sort of", "stuff", "basically", "i think", "maybe", "اعتقد", "ربما",
]  # fmt: skip
_EVASIVE = [
    "لا اعرف", "ما اعرف", "مش عارف", "لست متاكد", "نسيت", "ما ادري", "مدري", "زميلي",
    "صديقي", "i don't know", "i dont know", "dont know", "no idea", "forgot", "my friend",
    "skip", "pass", "التالي",
]  # fmt: skip


def _ar(language: str, ar: str, en: str) -> str:
    return ar if language == "ar" else en


def _identifier_parts(name: str) -> list[str]:
    """`calculateTotal` / `calculate_total` -> calculate, total (plus the full name)."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ")
    return [name] + [p for p in spaced.split() if len(p) > 2]


class TemplateProvider(Provider):
    name = "template"

    # -- questions ---------------------------------------------------------------------

    def generate_questions(self, context, language, count, examples, knowledge):
        questions: list[Question] = []
        add = questions.append
        title = context.get("title") or _ar(language, "المشروع", "the project")
        technologies = [t for t in context.get("technologies", [])][:4]
        functions = context.get("functions", [])
        tables = (context.get("database") or {}).get("tables", [])

        add(
            Question(
                key="understanding:purpose",
                type="understanding",
                level=1,
                text=_ar(
                    language,
                    f"ما المشكلة التي يحلّها مشروع «{title}»؟ ومن المستخدمون المستهدفون، وما "
                    "أهم ثلاث وظائف يقدّمها؟",
                    f"What problem does “{title}” solve, who are its users, and what are its "
                    "three most important features?",
                ),
                expected_points=[],
            )
        )
        for tech in technologies[:2]:
            add(
                Question(
                    key="understanding:technology",
                    type="understanding",
                    level=1,
                    text=_ar(
                        language,
                        f"لماذا اخترت {tech} في هذا المشروع؟ وما البديل الذي فكّرت فيه، ولماذا "
                        "لم تستخدمه؟",
                        f"Why did you choose {tech}? Which alternative did you consider and "
                        "why did you not use it?",
                    ),
                    expected_points=[tech],
                )
            )
        if architecture := context.get("architecture"):
            add(
                Question(
                    key="technical:architecture",
                    type="technical",
                    level=2,
                    text=_ar(
                        language,
                        f"المشروع مبني بنمط {architecture[0]}. صف مسار طلب واحد من الواجهة حتى "
                        "قاعدة البيانات، وأي ملفات يمر بها.",
                        f"The project uses {architecture[0]}. Walk through one request from the "
                        "UI to the database and name the files it passes through.",
                    ),
                    expected_points=["controller", "model", "view"],
                )
            )

        for function in functions[:4]:
            name, file = function["function"].split(".")[-1], function["file"]
            lines = f"{function['line']}-{function.get('end_line', function['line'])}"
            points = _identifier_parts(name)[:3] + function.get("calls", [])[:3]
            add(
                Question(
                    key="technical:explain_function",
                    type="technical",
                    level=2,
                    text=_ar(
                        language,
                        f"اشرح ما تفعله الدالة `{name}` في الملف `{file}`: ما مدخلاتها، وما "
                        "الذي تُرجعه، ومتى تُستدعى؟",
                        f"Explain what `{name}` in `{file}` does: its inputs, what it returns "
                        "and when it is called.",
                    ),
                    expected_points=points,
                    related_file=file,
                    related_lines=lines,
                    code=function.get("code"),
                )
            )
            if function.get("cyclomatic_complexity", 0) >= 8:
                add(
                    Question(
                        key="challenge:refactor",
                        type="challenge",
                        level=3,
                        text=_ar(
                            language,
                            f"تعقيد الدالة `{name}` الدوراني {function['cyclomatic_complexity']}. "
                            "كيف تعيد هيكلتها لتصبح أسهل في الفهم والاختبار؟",
                            f"`{name}` has cyclomatic complexity "
                            f"{function['cyclomatic_complexity']}. How would you refactor it?",
                        ),
                        expected_points=["extract", "function", "دالة", "تقسيم", "condition"],
                        related_file=file,
                        related_lines=lines,
                        code=function.get("code"),
                    )
                )
            add(
                Question(
                    key="verification:locate_function",
                    type="verification",
                    level=4,
                    text=_ar(
                        language,
                        f"بدون النظر إلى الكود: في أي ملف توجد الدالة `{name}`، وما الدوال أو "
                        "الجداول التي تتعامل معها؟",
                        f"Without looking at the code: which file contains `{name}`, and what "
                        "other functions or tables does it use?",
                    ),
                    expected_points=[file.rsplit("/", 1)[-1].rsplit(".", 1)[0]]
                    + function.get("calls", [])[:2],
                    related_file=file,
                    related_lines=lines,
                )
            )

        design = context.get("design") or {}
        for pattern in design.get("patterns", [])[:1]:
            owner = pattern["classes"][0]
            add(
                Question(
                    key="technical:design_pattern",
                    type="technical",
                    level=3,
                    text=_ar(
                        language,
                        f"في مشروعك نمط تصميم {pattern['pattern']} (في `{owner}`). ما المشكلة "
                        "التي يحلها هنا تحديداً؟ وماذا كان سيحدث لو لم تستخدمه؟",
                        f"Your project uses the {pattern['pattern']} pattern (in `{owner}`). "
                        "What problem does it solve here, and what would happen without it?",
                    ),
                    expected_points=[owner, *pattern["classes"][1:3]],
                )
            )
        for component in design.get("key_components", [])[:1]:
            name = component["name"]
            add(
                Question(
                    key="challenge:change_impact",
                    type="challenge",
                    level=3,
                    text=_ar(
                        language,
                        f"الدالة `{name}` يعتمد عليها {component['used_by']} أجزاء من المشروع. "
                        "لو احتجت تغيير مدخلاتها، ما الذي سيتأثر وكيف تتأكد أن شيئاً لم ينكسر؟",
                        f"`{name}` is used by {component['used_by']} parts of the project. If "
                        "you had to change its parameters, what would break and how would you "
                        "make sure nothing did?",
                    ),
                    expected_points=[name.split(".")[-1], "test", "اختبار"],
                    related_file=component["file"],
                )
            )
        _SOLID_POINTS = {
            "SRP": ["split", "class", "مسؤولية", "تقسيم"],
            "OCP": ["polymorphism", "interface", "تعدد الأشكال", "واجهة"],
            "LSP": ["inherit", "override", "وراثة", "الأصل"],
            "ISP": ["interface", "split", "واجهة", "تقسيم"],
            "DIP": ["inject", "constructor", "interface", "حقن", "واجهة"],
        }
        for issue in design.get("solid", [])[:1]:
            add(
                Question(
                    key="challenge:solid",
                    type="challenge",
                    level=4,
                    text=_ar(
                        language,
                        f"{issue['evidence_ar']}. كيف تعيد تصميم هذا الجزء ليتوافق مع مبدأ "
                        f"{issue['principle']}؟",
                        f"{issue['evidence']}. How would you redesign it to follow "
                        f"{issue['principle']}?",
                    ),
                    expected_points=_SOLID_POINTS.get(issue["principle"], []),
                )
            )

        for vulnerability in context.get("vulnerabilities", [])[:3]:
            kind = vulnerability["type"]
            add(
                Question(
                    key=f"challenge:vulnerability:{kind}",
                    type="challenge",
                    level=3,
                    text=_ar(
                        language,
                        f"في الملف `{vulnerability['file']}` السطر {vulnerability['line']} توجد "
                        f"ثغرة {kind}. كيف يمكن لمهاجم استغلالها، وكيف تُصلحها؟",
                        f"`{vulnerability['file']}` line {vulnerability['line']} has a {kind} "
                        "vulnerability. How could it be exploited and how would you fix it?",
                    ),
                    expected_points=_FIX_POINTS.get(kind, [])[:4],
                    related_file=vulnerability["file"],
                    related_lines=str(vulnerability["line"]),
                    code=vulnerability.get("evidence"),
                )
            )

        relations = [
            (table["name"], fk["ref_table"], fk["columns"])
            for table in tables
            for fk in table.get("foreign_keys", [])
        ]
        for child, parent, columns in relations[:2]:
            add(
                Question(
                    key="technical:relationship",
                    type="technical",
                    level=2,
                    text=_ar(
                        language,
                        f"ما العلاقة بين الجدولين {child} و {parent}؟ وما نوعها (واحد-لمتعدد أم "
                        "غيره)، وما الذي يحدث عند حذف سجل من {parent}؟",
                        f"What is the relationship between {child} and {parent}, what kind is "
                        f"it, and what happens when a row of {parent} is deleted?",
                    ),
                    expected_points=[*columns[:2], parent, child],
                )
            )
        for issue in (context.get("database") or {}).get("issues", [])[:2]:
            add(
                Question(
                    key=f"challenge:database:{issue['type']}",
                    type="challenge",
                    level=3,
                    text=_ar(
                        language,
                        f"في قاعدة البيانات: {issue['message']}. هل تتفق؟ وكيف تعدّل التصميم؟",
                        f"About the database: {issue['message']}. Do you agree, and how would "
                        "you change the design?",
                    ),
                    expected_points=[issue.get("table", "")] + list(issue.get("columns") or []),
                )
            )
        if tables:
            add(
                Question(
                    key="challenge:scaling",
                    type="challenge",
                    level=3,
                    text=_ar(
                        language,
                        "لو زاد عدد المستخدمين مئة ضعف، ما أول جزء في نظامك سيتأثر؟ وكيف تحسّنه؟",
                        "If users grew a hundredfold, which part of your system would suffer "
                        "first, and how would you improve it?",
                    ),
                    expected_points=["index", "فهرس", "cache", "query"],
                )
            )
        for inconsistency in (context.get("report") or {}).get("inconsistencies", [])[:2]:
            add(
                Question(
                    key=f"verification:report:{inconsistency['type']}",
                    type="verification",
                    level=4,
                    text=_ar(
                        language,
                        f"{inconsistency['report_claim']}، لكن: {inconsistency['code_reality']}. "
                        "فسّر هذا الاختلاف.",
                        f"{inconsistency['report_claim']}, but: {inconsistency['code_reality']}. "
                        "Explain the difference.",
                    ),
                    expected_points=[],
                )
            )
        return questions[: max(count, len(questions))]

    # -- grading -----------------------------------------------------------------------

    def evaluate(self, question, answer, language, examples):
        text = normalize(answer)
        words = [t.text for t in tokenize(answer)]
        if not words:
            return Evaluation(0, "evasive", "No answer.", 0.9)
        evasive_hits = [p for p in _EVASIVE if normalize(p) in text]
        if evasive_hits and len(words) < 12:
            return Evaluation(5, "evasive", "The student avoided the question.", 0.8)

        question_words = {t.text for t in tokenize(question.text)}
        new_words = [w for w in words if w not in question_words]
        if len(new_words) < max(3, len(words) // 4):
            return Evaluation(10, "evasive", "The answer mostly repeats the question.", 0.7)

        expected = [normalize(p) for p in question.expected_points if p.strip()]
        matched = [p for p in expected if p in text]
        coverage = len(matched) / len(expected) if expected else None
        length = min(1.0, len(new_words) / 30)
        # Concrete details: identifiers, numbers, code-like tokens.
        specific = sum(1 for w in set(new_words) if any(c.isdigit() or c == "_" for c in w))
        specific += len(re.findall(r"`[^`]+`|\w+\(\)|\w+\.\w+", answer))
        specificity = min(1.0, specific / 3)

        if coverage is None:
            score = 100 * (0.65 * length + 0.35 * specificity)
        else:
            # sqrt gives fair partial credit: 1 of 3 points is a partial answer, not wrong.
            score = 100 * (0.6 * coverage**0.5 + 0.25 * length + 0.15 * specificity)
        vague = sum(1 for p in _VAGUE if normalize(p) in text)
        score = max(0.0, min(100.0, score - 12 * vague - (10 if evasive_hits else 0)))
        verdict = "correct" if score >= 70 else "partial" if score >= 40 else "wrong"

        details = []
        if coverage is not None:
            details.append(f"covered {len(matched)}/{len(expected)} expected points")
        details.append(f"{len(new_words)} words of own content")
        if vague:
            details.append(f"{vague} vague phrases")
        # Rules are least sure about open questions with no expected points.
        confidence = 0.55 if coverage is not None else 0.35
        return Evaluation(round(score, 1), verdict, "; ".join(details), confidence)
