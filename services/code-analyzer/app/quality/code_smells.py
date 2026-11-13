"""Threshold-based code smells (thresholds follow the project plan, week 6)."""

from dataclasses import dataclass

from app.analyzers.base_analyzer import FileAnalysis

LONG_METHOD_LINES = 50
GOD_CLASS_LINES = 500
GOD_CLASS_METHODS = 20
MAX_PARAMETERS = 5
MAX_CYCLOMATIC = 10
MAX_NESTING = 4


@dataclass
class CodeSmell:
    type: str
    file: str
    line: int
    symbol: str
    message: str


def detect_smells(analysis: FileAnalysis) -> list[CodeSmell]:
    smells: list[CodeSmell] = []

    def add(kind: str, line: int, symbol: str, message: str) -> None:
        smells.append(CodeSmell(kind, analysis.path, line, symbol, message))

    for func in analysis.functions:
        name = func.qualified_name
        if func.length > LONG_METHOD_LINES:
            add("long_method", func.line, name, f"{func.length} lines (max {LONG_METHOD_LINES})")
        if func.parameters > MAX_PARAMETERS:
            add(
                "too_many_parameters",
                func.line,
                name,
                f"{func.parameters} parameters (max {MAX_PARAMETERS})",
            )
        if func.cyclomatic_complexity > MAX_CYCLOMATIC:
            add(
                "high_complexity",
                func.line,
                name,
                f"cyclomatic complexity {func.cyclomatic_complexity} (max {MAX_CYCLOMATIC})",
            )
        if func.max_nesting > MAX_NESTING:
            add("deep_nesting", func.line, name, f"nesting depth {func.max_nesting}")

    for cls in analysis.classes:
        if cls.length > GOD_CLASS_LINES or len(cls.methods) > GOD_CLASS_METHODS:
            add(
                "god_class",
                cls.line,
                cls.name,
                f"{cls.length} lines, {len(cls.methods)} methods "
                f"(max {GOD_CLASS_LINES} lines / {GOD_CLASS_METHODS} methods)",
            )
    return smells
