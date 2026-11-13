"""Small helpers over tree-sitter trees.

Every walk is iterative: generated or pathological code (e.g. a 5,000-term string
concatenation) produces trees far deeper than Python's recursion limit.
"""

from collections.abc import Iterator
from functools import cache

from tree_sitter import Language, Node, Parser


@cache
def java_parser() -> Parser:
    import tree_sitter_java

    return Parser(Language(tree_sitter_java.language()))


def text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def walk(node: Node) -> Iterator[Node]:
    """All descendants (including `node`) in source order."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def first_error(root: Node) -> Node | None:
    if not root.has_error:
        return None
    return next((n for n in walk(root) if n.type == "ERROR" or n.is_missing), root)


def line_counts(root: Node, source: str, comment_types: set[str]) -> tuple[int, int, int, int]:
    """Return (total, code, comment, blank) line counts."""
    lines = source.splitlines()
    blank = {i for i, line in enumerate(lines) if not line.strip()}
    comment_rows: set[int] = set()
    code_rows: set[int] = set()
    for node in walk(root):
        if node.type in comment_types:
            comment_rows.update(range(node.start_point.row, node.end_point.row + 1))
        elif node.child_count == 0 and node.end_byte > node.start_byte:
            code_rows.update(range(node.start_point.row, node.end_point.row + 1))
    comment = len(comment_rows - code_rows - blank)
    return len(lines), len(lines) - len(blank) - comment, comment, len(blank)


def snippet(node: Node, limit: int = 160) -> str:
    value = " ".join(text(node).split())
    return value if len(value) <= limit else value[: limit - 3] + "..."
