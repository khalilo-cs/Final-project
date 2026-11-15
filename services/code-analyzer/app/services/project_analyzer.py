"""Walk an extracted project and aggregate per-file analyses into one report."""

from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.analyzers.base_analyzer import BaseAnalyzer, FileAnalysis
from app.analyzers.cpp_analyzer import CppAnalyzer
from app.analyzers.csharp_analyzer import CSharpAnalyzer
from app.analyzers.java_analyzer import JavaAnalyzer
from app.analyzers.javascript_analyzer import JavaScriptAnalyzer
from app.analyzers.python_analyzer import PythonAnalyzer
from app.analyzers.technologies import MAX_MANIFEST_BYTES, TechnologyDetector
from app.quality.code_smells import detect_smells
from app.quality.dead_code import java_dead_code, python_dead_code
from app.quality.duplication import find_duplicates
from app.quality.score import quality_score, security_score
from app.security.cpp_rules import scan_cpp
from app.security.csharp_rules import scan_csharp
from app.security.java_rules import scan_java
from app.security.js_rules import scan_javascript
from app.security.models import Severity, Vulnerability
from app.security.python_rules import scan_python
from app.security.secrets_scanner import scan_secrets

ANALYZERS: list[BaseAnalyzer] = [
    PythonAnalyzer(), JavaAnalyzer(), JavaScriptAnalyzer(), CSharpAnalyzer(), CppAnalyzer(),
]  # fmt: skip
SECURITY_RULES = {
    "python": scan_python,
    "java": scan_java,
    "javascript": scan_javascript,
    "typescript": scan_javascript,
    "csharp": scan_csharp,
    "cpp": scan_cpp,
}
_BY_EXTENSION = {ext: analyzer for analyzer in ANALYZERS for ext in analyzer.extensions}

SKIPPED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env", "__pycache__",
    "dist", "build", "target", ".idea", ".vscode", "site-packages", "vendor",
    "bin", "obj", ".vs", "packages", "Debug", "Release", "x64", "cmake-build-debug",
}  # fmt: skip
# Text files worth scanning for secrets even without a language analyzer.
SECRET_SCAN_EXTENSIONS = {
    ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cs", ".cpp", ".cc", ".cxx", ".c", ".h",
    ".hpp", ".php", ".rb", ".go", ".json", ".yml", ".yaml", ".xml", ".properties",
    ".ini", ".cfg", ".conf", ".env", ".sql", ".sh",
}  # fmt: skip
MAX_FILE_BYTES = 1_000_000


def _project_files(root: Path):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIPPED_DIRS for part in relative.parts[:-1]):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        yield path, relative.as_posix()


def _is_scanned(path: Path) -> bool:
    return path.suffix.lower() in SECRET_SCAN_EXTENSIONS or path.name.startswith(".env")


def analyze_project(root: Path) -> dict:
    files: list[FileAnalysis] = []
    vulnerabilities: list[Vulnerability] = []
    skipped: list[dict] = []
    technologies = TechnologyDetector()

    python_sources: dict[str, str] = {}
    all_sources: dict[str, str] = {}
    dead: list[dict] = []
    for path, relative in _project_files(root):
        technologies.feed_path(relative)
        size = path.stat().st_size
        if technologies.wants_content(relative) and size <= MAX_MANIFEST_BYTES:
            technologies.feed_manifest(relative, path.read_text("utf-8", errors="replace"))
        if not _is_scanned(path):
            continue
        if size > MAX_FILE_BYTES:
            skipped.append({"file": relative, "reason": "file too large"})
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        vulnerabilities.extend(scan_secrets(relative, source))
        technologies.feed_text(relative, source.lower())
        analyzer = _BY_EXTENSION.get(path.suffix.lower())
        if analyzer is None:
            continue
        analysis = analyzer.analyze(relative, source)
        files.append(analysis)
        all_sources[relative] = source
        if analyzer.language == "python":
            python_sources[relative] = source
        elif analyzer.language == "java":
            dead.extend(java_dead_code(relative, source))
        technologies.feed_imports(relative, analysis.imports)
        if rules := SECURITY_RULES.get(analyzer.language):
            vulnerabilities.extend(rules(relative, source))

    dead.extend(python_dead_code(python_sources))
    duplication = find_duplicates(all_sources)
    return {
        "code": _code_summary(files, skipped, duplication, dead),
        "security": _security_summary(vulnerabilities),
        "stack": technologies.result(),
    }


def _code_summary(
    files: list[FileAnalysis], skipped: list[dict], duplication: dict, dead: list[dict]
) -> dict:
    functions = [func for file in files for func in file.functions]
    smells = [asdict(smell) for file in files for smell in detect_smells(file)]
    for block in duplication["duplicate_blocks"]:
        smells.append({
            "type": "duplicate_code", "file": block["other_file"], "line": block["other_lines"][0],
            "symbol": f"{block['file']}:{block['lines'][0]}-{block['lines'][1]}",
            "message": f"Lines {block['other_lines'][0]}-{block['other_lines'][1]} repeat "
            f"{block['file']}:{block['lines'][0]}-{block['lines'][1]}",
        })  # fmt: skip
    for item in dead:
        smells.append(
            {
                "type": "dead_code",
                "file": item["file"],
                "line": item["line"],
                "symbol": item["name"],
                "message": f"'{item['name']}' is never used",
            }
        )
    code_lines = sum(file.code_lines for file in files)
    unparsable = [file for file in files if file.parse_error]
    count = len(functions) or 1
    avg_cyclomatic = round(sum(f.cyclomatic_complexity for f in functions) / count, 2)
    avg_cognitive = round(sum(f.cognitive_complexity for f in functions) / count, 2)
    hotspots = sorted(functions, key=lambda f: f.cyclomatic_complexity, reverse=True)[:10]
    owner = {id(func): file.path for file in files for func in file.functions}

    return {
        "total_files": len(files),
        "total_lines": sum(file.total_lines for file in files),
        "code_lines": code_lines,
        "comment_lines": sum(file.comment_lines for file in files),
        "total_classes": sum(len(file.classes) for file in files),
        "total_functions": len(functions),
        "languages": dict(Counter(file.language for file in files)),
        "cyclomatic_complexity_avg": avg_cyclomatic,
        "cognitive_complexity_avg": avg_cognitive,
        "most_complex_functions": [
            {
                "file": owner[id(func)],
                "function": func.qualified_name,
                "line": func.line,
                "cyclomatic_complexity": func.cyclomatic_complexity,
                "cognitive_complexity": func.cognitive_complexity,
            }
            for func in hotspots
        ],
        "code_smells": smells,
        "code_smell_counts": dict(Counter(smell["type"] for smell in smells)),
        "code_duplication_percentage": duplication["code_duplication_percentage"],
        "duplicate_blocks": duplication["duplicate_blocks"],
        "dead_code": dead,
        "dead_code_lines": sum(item["lines"] for item in dead),
        "parse_errors": [{"file": f.path, "error": f.parse_error} for f in unparsable],
        "skipped_files": skipped,
        "overall_quality_score": quality_score(
            # Dead code is reported but not penalized: a function may be used from a
            # template, a script or dynamically, where static analysis cannot see it.
            avg_cyclomatic,
            sum(1 for smell in smells if smell["type"] != "dead_code"),
            code_lines,
            len(files),
            len(unparsable),
        ),
        "files": [asdict(file) for file in files],
    }


def _security_summary(vulnerabilities: list[Vulnerability]) -> dict:
    order = list(Severity)
    vulnerabilities.sort(key=lambda v: (order.index(v.severity), v.file, v.line))
    counts = {severity: 0 for severity in Severity}
    for vulnerability in vulnerabilities:
        counts[vulnerability.severity] += 1
    return {
        "vulnerabilities": [asdict(v) for v in vulnerabilities],
        "critical_count": counts[Severity.critical],
        "high_count": counts[Severity.high],
        "medium_count": counts[Severity.medium],
        "low_count": counts[Severity.low],
        "overall_security_score": security_score(counts),
    }
