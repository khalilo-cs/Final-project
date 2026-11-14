import difflib
import hashlib
from dataclasses import dataclass, field


@dataclass
class Edit:
    start: int  # character offsets in the file
    end: int
    replacement: str


@dataclass
class Fix:
    file: str
    line: int
    type: str  # vulnerability or issue it addresses
    title: str
    explanation: str
    kind: str  # "patch" (can be applied) or "suggestion" (advice only)
    edits: list[Edit] = field(default_factory=list)
    add_import: str | None = None  # e.g. "import os"
    example: str | None = None  # for suggestions: what the fix looks like
    id: str = ""

    def finalize(self, source: str) -> "Fix":
        after = apply_edits(source, self.edits, self.add_import) if self.kind == "patch" else ""
        digest = hashlib.sha256(f"{self.file}|{self.line}|{self.type}|{after}".encode())
        self.id = digest.hexdigest()[:12]
        return self

    def as_dict(self, source: str) -> dict:
        diff = None
        if self.kind == "patch":
            after = apply_edits(source, self.edits, self.add_import)
            diff = "".join(
                difflib.unified_diff(
                    source.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=f"a/{self.file}",
                    tofile=f"b/{self.file}",
                    n=2,
                )
            )
        return {
            "id": self.id,
            "file": self.file,
            "line": self.line,
            "type": self.type,
            "title": self.title,
            "explanation": self.explanation,
            "kind": self.kind,
            "diff": diff,
            "example": self.example,
        }


def apply_edits(source: str, edits: list[Edit], add_import: str | None = None) -> str:
    result = source
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        result = result[: edit.start] + edit.replacement + result[edit.end :]
    if add_import and add_import not in {line.strip() for line in result.splitlines()}:
        result = _insert_import(result, add_import)
    return result


def _insert_import(source: str, statement: str) -> str:
    """After a module docstring and `from __future__` imports, otherwise at the top."""
    import ast

    lines = source.splitlines(keepends=True)
    position = 0
    try:
        body = ast.parse(source).body
    except SyntaxError:
        body = []
    for node in body:
        is_docstring = (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
        is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
        if (is_docstring and position == 0) or is_future:
            position = node.end_lineno
        else:
            break
    return "".join(lines[:position]) + statement + "\n" + "".join(lines[position:])
