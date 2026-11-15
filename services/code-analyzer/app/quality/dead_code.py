"""Code that is never used (FR-03.7). Conservative: a false accusation is worse than a miss."""

import ast
import re

from tree_sitter import Node

from app.analyzers.treesitter import java_parser, text, walk


def _python_definitions(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node, node.name
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield member, member.name


def _python_uses(tree: ast.Module) -> set[str]:
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.alias):
            used.add(node.name.split(".")[-1])
            if node.asname:
                used.add(node.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used.update(re.findall(r"[A-Za-z_]\w+", node.value))  # getattr(x, "name"), __all__
    return used


def _skip(node, name: str) -> bool:
    return (
        name.startswith("__")  # dunder: called by Python itself
        or name.startswith(("test_", "Test"))  # test runners call these
        or name in {"main", "setUp", "tearDown", "run", "handle"}
        or bool(getattr(node, "decorator_list", None))  # routes, fixtures, properties...
    )


def python_dead_code(sources: dict[str, str]) -> list[dict]:
    trees = {}
    for path, source in sources.items():
        try:
            trees[path] = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError):
            continue
    used: set[str] = set()
    for tree in trees.values():
        used |= _python_uses(tree)
    unused = []
    for path, tree in trees.items():
        for node, name in _python_definitions(tree):
            if not _skip(node, name) and name not in used:
                unused.append(
                    {
                        "file": path,
                        "line": node.lineno,
                        "name": name,
                        "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                    }
                )
    return unused


def java_dead_code(path: str, source: str) -> list[dict]:
    """Private methods never called in their own file (private: nothing else can call them)."""
    root = java_parser().parse(source.encode("utf-8", errors="replace")).root_node
    called = {
        text(n.child_by_field_name("name")) for n in walk(root) if n.type == "method_invocation"
    }
    called |= {text(n.child_by_field_name("name")) for n in walk(root)
               if n.type == "method_reference"}  # fmt: skip
    references = set(re.findall(r"::\s*(\w+)", source))
    unused = []
    for node in walk(root):
        if node.type != "method_declaration":
            continue
        modifiers = next((c for c in node.children if c.type == "modifiers"), None)
        if modifiers is None or "private" not in text(modifiers).split():
            continue
        if any(c.type in ("annotation", "marker_annotation") for c in modifiers.children):
            continue
        name = text(node.child_by_field_name("name"))
        if name not in called and name not in references:
            unused.append(
                {
                    "file": path,
                    "line": node.start_point.row + 1,
                    "name": name,
                    "lines": node.end_point.row - node.start_point.row + 1,
                }
            )
    return unused


_ = Node  # tree-sitter type used in annotations of helpers
