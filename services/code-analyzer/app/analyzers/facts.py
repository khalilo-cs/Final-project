"""What a function body does: calls, objects created, SQL tables, type checks.

Shared by every analyzer so the knowledge graph is built the same way for all languages.
"""

import ast
import re
from collections import Counter

from tree_sitter import Node

from app.analyzers.base_analyzer import FunctionInfo
from app.analyzers.treesitter import text, walk

_CALLS = {"call_expression", "method_invocation", "invocation_expression",
          "function_call_expression", "member_call_expression"}  # fmt: skip
_NEW = {"object_creation_expression", "new_expression"}
_TYPE_CHECKS = {"instanceof_expression", "is_pattern_expression", "is_expression"}
_THROWS = {"throw_statement", "throw_expression"}
_SKIP_STATEMENTS = {"comment", "line_comment", "block_comment", "{", "}"}
_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
_SQL = re.compile(
    r"\b(?:from|join|into|update|table)\s+[`\"\[]?([A-Za-z_][\w]*)[`\"\]]?", re.IGNORECASE
)
_SQL_START = re.compile(r"^\s*(select|insert|update|delete|create|alter|drop|with)\b", re.I)
_NOT_TABLES = {"select", "where", "set", "values", "dual", "the", "a", "an", "if", "exists"}
MAX_ITEMS = 60


def _last_identifier(value: str) -> str:
    names = _IDENTIFIER.findall(value)
    return names[-1] if names else ""


def sql_tables(strings: list[str]) -> list[str]:
    tables: list[str] = []
    for value in strings:
        if not _SQL_START.match(value):
            continue
        for name in _SQL.findall(value):
            if name.lower() not in _NOT_TABLES and name.lower() not in tables:
                tables.append(name.lower())
    return tables


def _unique(items: list[str]) -> list[str]:
    return [name for name, _ in Counter(i for i in items if i).most_common(MAX_ITEMS)]


def _call_name(node: Node) -> str:
    """ "name" for a plain call, "receiver.name" for a member call (this/self kept)."""
    if node.type == "method_invocation":
        receiver = node.child_by_field_name("object")
        name = text(node.child_by_field_name("name"))
        return f"{_last_identifier(text(receiver))}.{name}" if receiver is not None else name
    target = node.child_by_field_name("function") or node.child_by_field_name("name")
    if target is None and node.named_children:
        target = node.named_children[0]
    names = _IDENTIFIER.findall(text(target).split("(")[0])
    if not names:
        return ""
    return f"{names[-2]}.{names[-1]}" if len(names) >= 2 else names[-1]


def ts_facts(info: FunctionInfo, body: Node | None) -> None:
    if body is None:
        return
    calls, created, strings = [], [], []
    for node in walk(body):
        kind = node.type
        if kind in _CALLS:
            name = _call_name(node)
            calls.append(name)
            if name.rsplit(".", 1)[-1] in ("isinstance", "is_a"):
                info.type_checks += 1
        elif kind in _NEW:
            target = node.child_by_field_name("type") or node.child_by_field_name("constructor")
            created.append(_last_identifier(text(target).split("<")[0]))
        elif kind in _TYPE_CHECKS or (
            kind == "binary_expression" and "instanceof" in [c.type for c in node.children]
        ):
            info.type_checks += 1
        elif kind in ("string_literal", "string", "template_string", "verbatim_string_literal",
                      "raw_string_literal", "encapsed_string"):  # fmt: skip
            strings.append(text(node).strip("@$\"'`"))
    info.calls = _unique(calls)
    info.instantiates = _unique(created)
    info.sql_tables = sql_tables(strings)
    statements = [c for c in body.named_children if c.type not in _SKIP_STATEMENTS]
    info.empty = not statements
    info.only_raises = bool(statements) and all(s.type in _THROWS or (
        s.type == "expression_statement" and s.named_children
        and s.named_children[0].type in _THROWS) for s in statements)  # fmt: skip


def py_facts(info: FunctionInfo, function: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
    calls, created, strings = [], [], []
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                receiver = target.value
                owner = receiver.id if isinstance(receiver, ast.Name) else (
                    receiver.attr if isinstance(receiver, ast.Attribute) else "")  # fmt: skip
                name = target.attr
                calls.append(f"{owner}.{name}" if owner else name)
            else:
                name = target.id if isinstance(target, ast.Name) else ""
                calls.append(name)
            if name[:1].isupper():
                created.append(name)  # Python creates objects by calling the class
            if name == "isinstance":
                info.type_checks += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
    info.calls = _unique(calls)
    info.instantiates = _unique(created)
    info.sql_tables = sql_tables(strings)
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # docstring
    info.empty = all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(
        s.value, ast.Constant) and s.value.value is Ellipsis) for s in body)  # fmt: skip
    info.only_raises = bool(body) and all(isinstance(s, ast.Raise) for s in body)
