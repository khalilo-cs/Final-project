"""Split source files into functions and describe each one by its structure.

The structural description is language-neutral: a `for` in Java and a `while` in
Python are both LOOP, every call is CALL plus the called name (API names such as
executeQuery survive, variable names do not). Two functions that do the same thing
the same way look alike even after renaming, reordering independent statements,
swapping loop kinds or rewriting in a similar language.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from tree_sitter import Language, Node, Parser

from app.analyzers.tokens import IGNORED_PATH_PARTS

MAX_FILE_BYTES = 300_000

_GRAMMARS = {
    ".py": "python", ".java": "java", ".js": "javascript", ".jsx": "javascript",
    ".mjs": "javascript", ".ts": "typescript", ".tsx": "tsx", ".cs": "c_sharp",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c": "cpp", ".h": "cpp", ".hpp": "cpp",
    ".php": "php",
}  # fmt: skip
_FUNCTIONS = {
    "function_definition", "method_declaration", "constructor_declaration",
    "function_declaration", "method_definition", "local_function_statement",
    "arrow_function", "function_expression", "generator_function_declaration",
}  # fmt: skip


@cache
def parser(grammar: str) -> Parser:
    if grammar == "python":
        import tree_sitter_python as module

        language = module.language()
    elif grammar == "java":
        import tree_sitter_java as module

        language = module.language()
    elif grammar == "javascript":
        import tree_sitter_javascript as module

        language = module.language()
    elif grammar in ("typescript", "tsx"):
        import tree_sitter_typescript as module

        language = module.language_tsx() if grammar == "tsx" else module.language_typescript()
    elif grammar == "c_sharp":
        import tree_sitter_c_sharp as module

        language = module.language()
    elif grammar == "cpp":
        import tree_sitter_cpp as module

        language = module.language()
    else:
        import tree_sitter_php as module

        language = module.language_php()
    return Parser(Language(language))


# Node type -> neutral category, checked in order (first match wins).
_CATEGORIES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(^|_)(for|while|do|foreach|loop)(_|$)|for_range|for_in"), "LOOP"),
    (re.compile(r"(^|_)(if|elif|else|conditional|ternary)(_|$)"), "COND"),
    (re.compile(r"switch|match_statement|case"), "SWITCH"),
    (re.compile(r"(^|_)(try|catch|except|finally)(_|$)"), "TRY"),
    (re.compile(r"throw|raise"), "THROW"),
    (re.compile(r"return"), "RETURN"),
    (re.compile(r"break|continue"), "JUMP"),
    (re.compile(r"object_creation|new_expression"), "NEW"),
    (re.compile(r"call|invocation"), "CALL"),
    (re.compile(r"lambda|arrow_function|anonymous"), "LAMBDA"),
    (re.compile(r"augmented_assignment|compound_assignment|update_expression"), "UPDATE"),
    (re.compile(r"assignment|declarator|variable_declaration|local_declaration"), "ASSIGN"),
    (re.compile(r"subscript|array_access|element_access|index"), "INDEX"),
    (re.compile(r"(^|_)(binary|boolean_operator|comparison)"), "BIN"),
    (re.compile(r"unary|not_operator"), "UNARY"),
    (re.compile(r"string|template"), "STR"),
    (re.compile(r"integer|float|number|decimal"), "NUM"),
    (re.compile(r"(^|_)(list|array|dictionary|object|tuple|set)(_|$)|initializer"), "COLLECTION"),
]
# Pieces that only differ in spelling between languages.
_OPERATORS = {"and": "&&", "or": "||", "not": "!", "===": "==", "!==": "!=", "is": "=="}


@cache
def category(node_type: str) -> str | None:
    for pattern, name in _CATEGORIES:
        if pattern.search(node_type):
            return name
    return None


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", "replace") if node is not None and node.text else ""


def _called_name(node: Node) -> str:
    target = (
        node.child_by_field_name("function")
        or node.child_by_field_name("name")
        or node.child_by_field_name("method")
        or (node.named_children[0] if node.named_children else None)
    )
    name = re.split(r"[.\->:]+", _text(target).strip())[-1]
    return name.lower()[:40] if re.fullmatch(r"[A-Za-z_]\w*", name or "") else ""


def _operator(node: Node) -> str:
    operator = node.child_by_field_name("operator")
    if operator is None:
        operator = next((c for c in node.children if not c.is_named), None)
    value = operator.type if operator is not None else ""
    return _OPERATORS.get(value, value)


def structure(body: Node) -> list[str]:
    """Pre-order categories with call names and operators: the function's shape."""
    shape: list[str] = []
    stack = [body]
    while stack:
        node = stack.pop()
        kind = category(node.type) if node.is_named else None
        if kind == "CALL":
            name = _called_name(node)
            shape.append(f"CALL:{name}" if name else "CALL")
        elif kind == "BIN":
            shape.append(f"BIN:{_operator(node)}")
        elif kind is not None:
            shape.append(kind)
        if kind in ("STR", "NUM"):
            continue  # literal contents say nothing about the logic
        stack.extend(reversed(node.children))
    return shape


@dataclass
class Unit:
    file: str
    name: str
    start_line: int
    end_line: int
    shape: list[str]
    source: str = field(repr=False)

    @property
    def lines(self) -> int:
        return self.end_line - self.start_line + 1


def _name(node: Node) -> str:
    named = node.child_by_field_name("name")
    if named is None and (declarator := node.child_by_field_name("declarator")) is not None:
        while declarator.child_by_field_name("declarator") is not None:
            declarator = declarator.child_by_field_name("declarator")
        named = declarator
    if named is None and node.parent is not None:  # const f = () => ...
        named = node.parent.child_by_field_name("name")
    return _text(named)[:100] or "<anonymous>"


def file_units(relative: str, source: str, min_shape: int) -> Iterator[Unit]:
    grammar = _GRAMMARS.get(Path(relative).suffix.lower())
    if grammar is None:
        return
    root = parser(grammar).parse(source.encode("utf-8", "replace")).root_node
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _FUNCTIONS:
            body = node.child_by_field_name("body") or node
            shape = structure(body)
            if len(shape) >= min_shape:
                yield Unit(relative, _name(node), node.start_point.row + 1,
                           node.end_point.row + 1, shape, _text(node))  # fmt: skip
        stack.extend(reversed(node.children))


def project_units(root: Path, min_shape: int) -> list[Unit]:
    units: list[Unit] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in _GRAMMARS:
            continue
        if set(relative.parts[:-1]) & IGNORED_PATH_PARTS or ".min." in path.name:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        units.extend(file_units(relative.as_posix(), source, min_shape))
    return units
