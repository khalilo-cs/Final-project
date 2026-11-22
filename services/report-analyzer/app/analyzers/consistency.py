"""Does the report describe the project that was actually submitted? (FR-06.3, FR-06.4)

`facts` come from the code and database analyzers:
    {"languages": {"Java": 12}, "technologies": ["Spring Boot", "MySQL"],
     "architecture": ["MVC"], "total_tables": 7,
     "tables": ["users", "orders"], "classes": ["User", "OrderService"]}

It also checks the report's database description against the real schema
(FR-05.7) and the class names in its UML diagrams against the code (FR-06.5).
"""

import re
from dataclasses import asdict, dataclass

from app.text.normalize import normalize

# Canonical name -> patterns matched against the normalized report text.
# Only technologies the code analyzer can actually detect are listed.
_LANGUAGES = {
    "Python": [r"\bpython\b", r"بايثون"],
    "Java": [r"\bjava\b(?!\s*script)", r"جافا(?!\s*سكربت)"],
    "JavaScript": [r"\bjavascript\b", r"\bjs\b", r"جافا\s*سكربت"],
    "TypeScript": [r"\btypescript\b"],
    "PHP": [r"\bphp\b"],
    "C#": [r"(?<!\w)c#", r"\bc\s*sharp\b", r"سي\s*شارب"],
    "C++": [r"(?<!\w)c\+\+"],
    "Dart": [r"\bdart\b"],
    "Kotlin": [r"\bkotlin\b", r"كوتلن"],
}
_TECHNOLOGIES = {
    "React": [r"\breact(?:\.?js)?\b(?!\s*native)", r"رياكت"],
    "React Native": [r"\breact\s*native\b"],
    "Vue.js": [r"\bvue(?:\.?js)?\b"],
    "Angular": [r"\bangular\b"],
    "Express": [r"\bexpress(?:\.?js)?\b"],
    "Django": [r"\bdjango\b", r"جانغو", r"دجانغو"],
    "Flask": [r"\bflask\b", r"فلاسك"],
    "FastAPI": [r"\bfastapi\b"],
    "Laravel": [r"\blaravel\b", r"لارافيل"],
    "Spring": [r"\bspring\b(?!\s*boot)"],
    "Spring Boot": [r"\bspring\s*boot\b"],
    "Flutter": [r"\bflutter\b", r"فلاتر"],
    "Android": [r"\bandroid\b", r"اندرويد"],
    "MySQL": [r"\bmysql\b", r"ماي\s*اس\s*كيو\s*ال"],
    "PostgreSQL": [r"\bpostgres(?:ql)?\b"],
    "MongoDB": [r"\bmongo(?:db)?\b", r"مونجو"],
    "SQLite": [r"\bsqlite\b"],
    "Firebase": [r"\bfirebase\b", r"فايربيس"],
    "TensorFlow": [r"\btensorflow\b"],
    "PyTorch": [r"\bpytorch\b"],
    "Bootstrap": [r"\bbootstrap\b"],
    "SQL Server": [r"\bsql\s*server\b", r"\bmssql\b", r"اس\s*كيو\s*ال\s*سيرفر"],
    "MS Access": [r"\b(?:ms|microsoft)\s*access\b", r"اكسس"],
    "Windows Forms": [r"\bwindows\s*forms?\b", r"\bwinforms?\b"],
    "WPF": [r"\bwpf\b"],
    "ASP.NET": [r"\basp\s*\.?\s*net\b"],
    "ASP.NET Core": [r"\basp\s*\.?\s*net\s*core\b"],
    "ASP.NET MVC": [r"\basp\s*\.?\s*net\s*mvc\b"],
    "Entity Framework": [r"\bentity\s*framework\b"],
    "Qt": [r"\bqt\b"],
    "OpenCV": [r"\bopencv\b"],
}
# Technologies implied by others (Spring Boot implies Spring, JPA/Hibernate etc.).
_IMPLIES = {
    "Spring Boot": {"Spring"}, "React Native": {"React"},
    "ASP.NET Core": {"ASP.NET"}, "ASP.NET MVC": {"ASP.NET"},
}  # fmt: skip
_MVC = [r"\bmvc\b", r"model[\s-]*view[\s-]*controller"]
_TABLE_COUNT = [
    re.compile(r"(\d{1,3})\s*(?:جداول|جدولا|جدول)"),
    re.compile(r"(\d{1,3})\s+(?:database\s+)?tables\b"),
]


# "the users table", "جدول المستخدمين users", "table `orders`"
_TABLE_NAMED = [
    re.compile(r"(?:جدول|الجدول)\s*[\"'`«(]?\s*([A-Za-z][A-Za-z0-9_]{2,40})"),
    re.compile(r"\btable\s*[\"'`«(]\s*([A-Za-z][A-Za-z0-9_]{2,40})"),
    re.compile(r"\b([A-Za-z][A-Za-z0-9_]{2,40})\s+table\b", re.I),
]
_NOT_TABLES = {
    "the", "this", "that", "each", "every", "one", "following", "above", "below", "main",
    "database", "data", "lookup", "join", "hash", "of", "and", "with", "in", "is", "are",
    "contents", "summary", "periodic", "truth", "routing", "symbol",
}  # fmt: skip
_UML_DIAGRAMS = {
    "class": [r"class\s+diagram", r"مخطط\s+(?:ال)?(?:فئات|كلاسات|اصناف|صنف)"],
    "use_case": [r"use[\s-]*case", r"حالات\s+(?:ال)?استخدام"],
    "sequence": [r"sequence\s+diagram", r"مخطط\s+(?:ال)?تسلسل"],
    "activity": [r"activity\s+diagram", r"مخطط\s+(?:ال)?(?:نشاط|انشطة)"],
    "er": [r"\berd?\b\s*diagram", r"entity[\s-]*relationship", r"مخطط\s+(?:ال)?كيانات"],
    "deployment": [r"deployment\s+diagram", r"مخطط\s+(?:ال)?نشر"],
}
_UML_WORD = re.compile(r"\buml\b|class\s+diagram|مخطط\s+(?:ال)?(?:فئات|كلاسات|اصناف)")
# CamelCase words in the original (not case-folded) text: likely class names.
_CAMEL = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
_CLASS_NAMED = re.compile(r"\b(?:class|كلاس|الكلاس|الصنف|صنف)\s+[\"'`«]?([A-Z][A-Za-z0-9_]{2,40})")
_COMMON_CAMEL = {
    "JavaScript", "TypeScript", "PostgreSQL", "MySQL", "GitHub", "PowerPoint", "YouTube",
    "WhatsApp", "PayPal", "LinkedIn", "WordPress", "MongoDB", "FastAPI", "SpringBoot",
    "PyTorch", "TensorFlow", "OpenCV", "iPhone", "DevOps", "PhpMyAdmin", "VisualStudio",
}  # fmt: skip


@dataclass
class Inconsistency:
    type: str
    severity: str
    report_claim: str
    code_reality: str
    evidence: str | None = None


def _mentions(text: str, patterns: list[str]) -> list[re.Match]:
    return [m for pattern in patterns for m in re.finditer(pattern, text)]


def _context(original: str, normalized: str, match: re.Match) -> str:
    # Normalization can change length slightly; show the surrounding normalized text.
    start, end = max(0, match.start() - 80), min(len(normalized), match.end() + 80)
    return " ".join(normalized[start:end].split())


def check_consistency(text: str, facts: dict | None) -> dict:
    normalized = normalize(text)
    claimed = {
        name: _mentions(normalized, patterns)
        for name, patterns in {**_LANGUAGES, **_TECHNOLOGIES}.items()
    }
    claimed = {name: found for name, found in claimed.items() if found}
    result = {
        "mentioned_technologies": {name: len(found) for name, found in claimed.items()},
        "inconsistencies": [],
        "checked": facts is not None,
    }
    if not facts:
        return result

    languages = set(facts.get("languages") or {})
    detected = set(facts.get("technologies") or [])
    technologies = set(detected)
    for name in detected:
        technologies |= _IMPLIES.get(name, set())
    mentioned = set(claimed)
    for name in claimed:
        mentioned |= _IMPLIES.get(name, set())
    inconsistencies: list[Inconsistency] = []

    for name, found in claimed.items():
        actual = languages if name in _LANGUAGES else technologies
        if name in actual or (not languages and not technologies):
            continue
        times = len(found)
        inconsistencies.append(
            Inconsistency(
                type="claimed_not_found",
                # One passing mention may be the literature review; repeated ones are a claim.
                severity="Medium" if times >= 3 else "Low",
                report_claim=f"The report mentions {name} ({times} times)",
                code_reality=f"No {name} found in the submitted code",
                evidence=_context(text, normalized, found[0]),
            )
        )

    for name in sorted(detected & set(_TECHNOLOGIES)):
        if name not in mentioned:
            inconsistencies.append(
                Inconsistency(
                    type="undocumented",
                    severity="Low",
                    report_claim=f"The report never mentions {name}",
                    code_reality=f"The code uses {name}",
                )
            )

    if (found := _mentions(normalized, _MVC)) and "MVC" not in (facts.get("architecture") or []):
        inconsistencies.append(
            Inconsistency(
                type="architecture_mismatch",
                severity="Medium" if len(found) >= 2 else "Low",
                report_claim="The report describes an MVC architecture",
                code_reality="The folder structure shows no controllers/models/views separation",
                evidence=_context(text, normalized, found[0]),
            )
        )

    total_tables = facts.get("total_tables")
    if total_tables:
        for pattern in _TABLE_COUNT:
            match = pattern.search(normalized)
            if match and 0 < int(match[1]) != total_tables:
                inconsistencies.append(
                    Inconsistency(
                        type="table_count_mismatch",
                        severity="Medium",
                        report_claim=f"The report states {match[1]} tables",
                        code_reality=f"The submitted database has {total_tables} tables",
                        evidence=_context(text, normalized, match),
                    )
                )
                break

    inconsistencies.extend(_check_tables(text, normalized, facts.get("tables")))
    uml, uml_issues = _check_uml(text, normalized, facts.get("classes"))
    inconsistencies.extend(uml_issues)
    result["uml"] = uml

    result["inconsistencies"] = [asdict(i) for i in inconsistencies]
    return result


def _plain(name: str) -> str:
    return name.lower().replace("_", "")


def _check_tables(text: str, normalized: str, tables: list[str] | None) -> list[Inconsistency]:
    """Tables the report names that the submitted schema does not have (FR-05.7)."""
    if not tables:
        return []
    real = {_plain(t) for t in tables}
    real |= {name[:-1] for name in real if name.endswith("s")} | {name + "s" for name in real}
    found: list[Inconsistency] = []
    seen: set[str] = set()
    for pattern in _TABLE_NAMED:
        for match in pattern.finditer(normalized):
            name = match[1]
            key = _plain(name)
            if key in _NOT_TABLES or key in seen or key in real:
                continue
            seen.add(key)
            found.append(
                Inconsistency(
                    type="table_not_in_schema",
                    severity="Medium",
                    report_claim=f"The report describes a table named '{name}'",
                    code_reality="The submitted database has no such table",
                    evidence=_context(text, normalized, match),
                )
            )
    return found[:10]


def _check_uml(
    text: str, normalized: str, classes: list[str] | None
) -> tuple[dict, list[Inconsistency]]:
    """Do the classes drawn in the report's UML diagrams exist in the code? (FR-06.5)"""
    diagrams = sorted(
        kind for kind, patterns in _UML_DIAGRAMS.items() if _mentions(normalized, patterns)
    )
    uml = {"has_uml": bool(_UML_WORD.search(normalized)), "diagrams": diagrams}
    if not classes or "class" not in diagrams:
        return uml, []
    real = {name.lower() for name in classes}
    named = {m[1] for m in _CLASS_NAMED.finditer(text)}
    camel = {m[0] for m in _CAMEL.finditer(text)} - _COMMON_CAMEL
    candidates = named | camel
    matched = sorted(name for name in candidates if name.lower() in real)
    missing = sorted(name for name in candidates if name.lower() not in real)
    # Without a single match the CamelCase words are probably not class names at all.
    if not matched:
        missing = sorted(named - {n for n in named if n.lower() in real})
    documented = len({name.lower() for name in matched})
    uml.update(
        classes_in_report=len(candidates),
        classes_matched=matched,
        classes_not_in_code=missing[:20],
        code_classes_documented_pct=round(100 * documented / len(real), 1),
    )
    issues = []
    if missing:
        issues.append(
            Inconsistency(
                type="uml_class_not_found",
                severity="Medium" if len(missing) >= 3 else "Low",
                report_claim="The report's class diagram shows: " + ", ".join(missing[:8]),
                code_reality="These classes do not exist in the submitted code",
            )
        )
    return uml, issues
