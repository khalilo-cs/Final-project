"""Deterministic fixes for Python findings. Only rewrites whose meaning is certain."""

import ast
import re

from app.fixes.models import Edit, Fix
from app.security.python_rules import _SQL_METHODS, _dotted, _looks_like_sql

_SIMPLE = (ast.Name, ast.Attribute, ast.Subscript)
_SECRET_NAME = re.compile(r"(password|passwd|secret|api_?key|token|access_?key)", re.I)


class _Offsets:
    def __init__(self, source: str) -> None:
        self.starts = [0]
        for line in source.splitlines(keepends=True):
            self.starts.append(self.starts[-1] + len(line))
        self.source = source

    def of(self, line: int, col: int) -> int:
        # ast columns are UTF-8 byte offsets; convert to character offsets.
        line_text = self.source[self.starts[line - 1] : self.starts[line]]
        return self.starts[line - 1] + len(line_text.encode()[:col].decode(errors="ignore"))

    def span(self, node: ast.AST) -> tuple[int, int]:
        return self.of(node.lineno, node.col_offset), self.of(node.end_lineno, node.end_col_offset)


def _sql_parts(node: ast.AST) -> list | None:
    """Split a dynamically built SQL string into literal text and simple expressions."""
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) or (
                isinstance(value, ast.FormattedValue)
                and value.conversion == -1
                and value.format_spec is None
                and isinstance(value.value, _SIMPLE)
            ):
                parts.append(value.value)
            else:
                return None
        return parts
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _sql_parts(node.left), _sql_parts(node.right)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, _SIMPLE):
        return [node]
    return None


def _parameterize(parts: list, placeholder: str, source: str) -> tuple[str, list[str]] | None:
    text, params = "", []
    for index, part in enumerate(parts):
        if isinstance(part, str):
            text += part
            continue
        # '{name}' -> ? : the driver quotes the value itself.
        following = parts[index + 1] if index + 1 < len(parts) else ""
        if text.endswith(("'", '"')) and isinstance(following, str) and following[:1] == text[-1]:
            text = text[:-1]
            parts[index + 1] = following[1:]
        text += placeholder
        params.append(ast.get_source_segment(source, part))
    if not params or any(p is None for p in params):
        return None
    return text, params


def propose_python(path: str, source: str) -> list[Fix]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return []
    offsets = _Offsets(source)
    imports = {alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names}
    placeholder = "?" if "sqlite3" in imports else "%s"
    fixes: list[Fix] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            method = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if method in _SQL_METHODS and len(node.args) == 1 and not node.keywords:
                fixes.extend(_sql_fix(path, source, offsets, node, placeholder))
            elif name in ("yaml.load", "yaml.load_all") and not node.keywords:
                start, end = offsets.span(node.func)
                fixes.append(
                    Fix(path, node.lineno, "Insecure Deserialization",
                        "Use yaml.safe_load instead of yaml.load",
                        "yaml.load can build arbitrary Python objects from the file; safe_load "
                        "only builds plain data.",
                        "patch", [Edit(start, end, name.replace("load", "safe_load"))])
                )  # fmt: skip
            for keyword in node.keywords:
                value = keyword.value
                if not isinstance(value, ast.Constant):
                    continue
                if (
                    keyword.arg == "verify"
                    and value.value is False
                    and name.startswith(("requests.", "httpx."))
                ):
                    start, end = offsets.span(value)
                    fixes.append(
                        Fix(path, node.lineno, "Disabled TLS Verification",
                            "Turn TLS certificate verification back on",
                            "verify=False accepts any certificate, so traffic can be "
                            "intercepted.", "patch", [Edit(start, end, "True")])
                    )  # fmt: skip
                if keyword.arg == "debug" and value.value is True and name.endswith(".run"):
                    start, end = offsets.span(value)
                    fixes.append(
                        Fix(path, node.lineno, "Debug Mode Enabled",
                            "Disable debug mode",
                            "The debugger lets anyone who reaches the page run code on the "
                            "server. Use debug mode only on your own machine.",
                            "patch", [Edit(start, end, "False")])
                    )  # fmt: skip
            if name in ("hashlib.md5", "hashlib.sha1"):
                fixes.append(
                    Fix(path, node.lineno, "Weak Hash Algorithm",
                        f"Replace {name} for passwords with bcrypt",
                        "Not applied automatically: existing stored hashes would stop "
                        "matching. Migrate by re-hashing at the next successful login.",
                        "suggestion",
                        example="import bcrypt\nhashed = bcrypt.hashpw(password.encode(), "
                        "bcrypt.gensalt())\nok = bcrypt.checkpw(password.encode(), hashed)")
                )  # fmt: skip

        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and _SECRET_NAME.search(node.targets[0].id)
            and len(node.value.value) >= 6
            and node.col_offset == 0
        ):
            variable = node.targets[0].id
            start, end = offsets.span(node.value)
            fixes.append(
                Fix(path, node.lineno, "Hardcoded Secret",
                    f"Read {variable} from an environment variable",
                    f"The secret is visible to anyone with the code. After this change set "
                    f"{variable.upper()} in the environment (or a .env file kept out of Git).",
                    "patch", [Edit(start, end, f'os.environ["{variable.upper()}"]')],
                    add_import="import os")
            )  # fmt: skip
    return [fix.finalize(source) for fix in fixes]


def _sql_fix(path, source, offsets, call, placeholder) -> list[Fix]:
    argument = call.args[0]
    if isinstance(argument, ast.Call) and _dotted(argument.func).endswith("text"):
        return []  # sqlalchemy.text needs named :params; leave as advice from the scanner
    if not _looks_like_sql(argument) or isinstance(argument, ast.Constant):
        return []
    parts = _sql_parts(argument)
    result = _parameterize(list(parts), placeholder, source) if parts else None
    if result is None:
        return [
            Fix(path, call.lineno, "SQL Injection", "Use a parameterized query",
                "The query is built in a way that cannot be rewritten automatically. Pass "
                "values separately so the database never treats them as SQL.", "suggestion",
                # Example text shown to the student (a parameterized query), not SQL we run.
                example=f'cursor.execute("SELECT * FROM users WHERE name = {placeholder}", '  # noqa: S608
                "(name,))")
        ]  # fmt: skip
    text, params = result
    start, end = offsets.span(argument)
    replacement = f"{text!r}, ({', '.join(params)},)"
    return [
        Fix(path, call.lineno, "SQL Injection", "Use a parameterized query",
            f"Values are now sent separately ({placeholder} placeholders), so input such as "
            "' OR 1=1 -- is treated as data, never as SQL.", "patch",
            [Edit(start, end, replacement)])
    ]  # fmt: skip
