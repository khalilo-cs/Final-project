"""Walk an extracted project and aggregate per-file analyses into one report."""

from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.analyzers.base_analyzer import BaseAnalyzer, FileAnalysis
from app.analyzers.python_analyzer import PythonAnalyzer
from app.quality.code_smells import detect_smells
from app.quality.score import quality_score, security_score
from app.security.models import Severity, Vulnerability
from app.security.python_rules import scan_python
from app.security.secrets_scanner import scan_secrets

ANALYZERS: list[BaseAnalyzer] = [PythonAnalyzer()]
_BY_EXTENSION = {ext: analyzer for analyzer in ANALYZERS for ext in analyzer.extensions}

SKIPPED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env", "__pycache__",
    "dist", "build", "target", ".idea", ".vscode", "site-packages", "vendor",
}  # fmt: skip
# Text files worth scanning for secrets even without a language analyzer.
SECRET_SCAN_EXTENSIONS = {
    ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cs", ".cpp", ".c", ".h", ".hpp", ".php",
    ".rb", ".go", ".json", ".yml", ".yaml", ".xml", ".properties", ".ini", ".cfg", ".conf",
    ".env", ".sql", ".sh",
}  # fmt: skip
MAX_FILE_BYTES = 1_000_000


def _source_files(root: Path):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIPPED_DIRS for part in relative.parts[:-1]):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() in SECRET_SCAN_EXTENSIONS or path.name.startswith(".env"):
            yield path, relative.as_posix()


def analyze_project(root: Path) -> dict:
    files: list[FileAnalysis] = []
    vulnerabilities: list[Vulnerability] = []
    skipped: list[dict] = []

    for path, relative in _source_files(root):
        if path.stat().st_size > MAX_FILE_BYTES:
            skipped.append({"file": relative, "reason": "file too large"})
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        vulnerabilities.extend(scan_secrets(relative, source))
        analyzer = _BY_EXTENSION.get(path.suffix.lower())
        if analyzer is None:
            continue
        files.append(analyzer.analyze(relative, source))
        if analyzer.language == "python":
            vulnerabilities.extend(scan_python(relative, source))

    return {
        "code": _code_summary(files, skipped),
        "security": _security_summary(vulnerabilities),
    }


def _code_summary(files: list[FileAnalysis], skipped: list[dict]) -> dict:
    functions = [func for file in files for func in file.functions]
    smells = [smell for file in files for smell in detect_smells(file)]
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
        "code_smells": [asdict(smell) for smell in smells],
        "code_smell_counts": dict(Counter(smell.type for smell in smells)),
        "parse_errors": [{"file": f.path, "error": f.parse_error} for f in unparsable],
        "skipped_files": skipped,
        "overall_quality_score": quality_score(
            avg_cyclomatic, len(smells), code_lines, len(files), len(unparsable)
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
