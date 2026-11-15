"""Language-independent result model shared by every analyzer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    line: int
    end_line: int
    parameters: int
    cyclomatic_complexity: int
    cognitive_complexity: int
    max_nesting: int
    is_async: bool = False
    is_generator: bool = False
    decorators: list[str] = field(default_factory=list)
    # What the body does (for the knowledge graph, design patterns and SOLID checks).
    calls: list[str] = field(default_factory=list)  # called names, last identifier
    instantiates: list[str] = field(default_factory=list)  # `new X` / X(...)
    sql_tables: list[str] = field(default_factory=list)  # tables named in SQL strings
    type_checks: int = 0  # instanceof / isinstance / `is` patterns
    empty: bool = False  # no statements
    only_raises: bool = False  # body only throws (e.g. NotImplemented)

    @property
    def length(self) -> int:
        return self.end_line - self.line + 1


@dataclass
class ClassInfo:
    name: str
    line: int
    end_line: int
    bases: list[str]
    methods: list[str]
    decorators: list[str] = field(default_factory=list)
    kind: str = "class"  # class / interface / abstract / enum / struct

    @property
    def length(self) -> int:
        return self.end_line - self.line + 1


@dataclass
class FileAnalysis:
    path: str
    language: str
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    imports: list[str] = field(default_factory=list)
    # Python `from pkg import mod`: "pkg.mod", which may be a module (knowledge graph).
    submodule_imports: list[str] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    parse_error: str | None = None


class BaseAnalyzer(ABC):
    language: str
    extensions: tuple[str, ...]

    @abstractmethod
    def analyze(self, path: str, source: str) -> FileAnalysis:
        """Analyze one source file. Must not raise on invalid code: set parse_error."""
