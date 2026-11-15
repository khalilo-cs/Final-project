"""Security rules for JavaScript/TypeScript (Node/Express back-ends and browser code)."""

import re

from tree_sitter import Node

from app.analyzers.javascript_analyzer import dialect_for
from app.analyzers.treesitter import js_parser, snippet, text, walk
from app.security.models import Severity, Vulnerability

_SQL_CALLS = {"query", "execute", "raw", "exec"}
_SQL_START = re.compile(r"^\s*(select|insert|update|delete|drop|create|alter)\b", re.I)
_COMMAND_CALLS = {"exec", "execSync", "spawn", "spawnSync"}
_HTML_SINKS = {"innerHTML", "outerHTML"}
_FILE_CALLS = {"readFile", "readFileSync", "createReadStream", "sendFile", "unlink", "unlinkSync",
               "writeFile", "writeFileSync"}  # fmt: skip
_REQUEST = re.compile(r"\breq(uest)?\.(params|query|body)\b")


def _call_name(call: Node) -> tuple[str, str]:
    """('db', 'query') for db.query(...), ('', 'exec') for exec(...)."""
    function = call.child_by_field_name("function")
    if function is None:
        return "", ""
    if function.type == "member_expression":
        return text(function.child_by_field_name("object")), text(
            function.child_by_field_name("property")
        )
    return "", text(function)


def _first_argument(call: Node) -> Node | None:
    arguments = call.child_by_field_name("arguments")
    return (
        arguments.named_children[0] if arguments is not None and arguments.named_children else None
    )


def _is_literal(node: Node) -> bool:
    if node.type == "string":
        return True
    if node.type == "template_string":
        return not any(c.type == "template_substitution" for c in node.named_children)
    return False


def _dynamic(node: Node) -> bool:
    """A value built from variable parts: `...${x}...`, "..." + x, or a plain variable."""
    if node.type == "template_string":
        return any(c.type == "template_substitution" for c in node.named_children)
    if node.type == "binary_expression":
        return not all(_is_literal(c) for c in node.named_children)
    return node.type in ("identifier", "member_expression", "call_expression")


def _sql_text(node: Node) -> bool:
    raw = text(node).strip("`'\" (")
    return bool(_SQL_START.match(raw)) or any(
        _SQL_START.match(text(c).strip("`'\""))
        for c in walk(node)
        if c.type in ("string", "string_fragment")
    )


class _Scanner:
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Vulnerability] = []
        self.sql_vars: set[str] = set()

    def add(self, kind, severity, node, description):
        self.findings.append(
            Vulnerability(
                kind, severity, self.path, node.start_point.row + 1, description, snippet(node)
            )
        )

    def scan(self, root: Node) -> None:
        for node in walk(root):
            if node.type == "variable_declarator":
                value = node.child_by_field_name("value")
                if (
                    value is not None
                    and _dynamic(value)
                    and value.type != "identifier"
                    and _sql_text(value)
                ):
                    self.sql_vars.add(text(node.child_by_field_name("name")))
            elif node.type == "call_expression":
                self.call(node)
            elif node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if (
                    left is not None and left.type == "member_expression"
                    and text(left.child_by_field_name("property")) in _HTML_SINKS
                    and right is not None and not _is_literal(right)
                ):  # fmt: skip
                    self.add(
                        "Cross-Site Scripting (XSS)",
                        Severity.high,
                        node,
                        "Untrusted text assigned to innerHTML; use textContent",
                    )
            elif node.type == "jsx_attribute" and "dangerouslySetInnerHTML" in text(node)[:40]:
                self.add(
                    "Cross-Site Scripting (XSS)",
                    Severity.medium,
                    node,
                    "dangerouslySetInnerHTML renders raw HTML; sanitize it first",
                )

    def call(self, node: Node) -> None:
        target, name = _call_name(node)
        argument = _first_argument(node)
        if argument is None:
            return
        if name in _SQL_CALLS and (
            (_dynamic(argument) and argument.type != "identifier" and _sql_text(argument))
            or (argument.type == "identifier" and text(argument) in self.sql_vars)
        ):
            self.add(
                "SQL Injection",
                Severity.critical,
                node,
                "SQL built with a template string or concatenation; pass values as "
                "parameters (? placeholders)",
            )
        elif (
            name in _COMMAND_CALLS and target in ("", "child_process", "cp") and _dynamic(argument)
        ):
            if name.startswith("exec") or "shell" in text(node):
                self.add(
                    "Command Injection",
                    Severity.critical,
                    node,
                    f"{name}() runs a shell command built from variable input",
                )
        elif name == "eval" or (name == "Function" and target == ""):
            if not _is_literal(argument):
                self.add(
                    "Code Injection",
                    Severity.high,
                    node,
                    f"{name}() executes dynamically built code",
                )
        elif name == "write" and target == "document" and not _is_literal(argument):
            self.add(
                "Cross-Site Scripting (XSS)",
                Severity.high,
                node,
                "document.write() with dynamic content",
            )
        elif name in _FILE_CALLS and _REQUEST.search(text(argument)):
            self.add(
                "Path Traversal",
                Severity.high,
                node,
                "File path built from request input; validate it against a base folder",
            )
        elif name == "createHash" and text(argument).strip("'\"`").lower() in ("md5", "sha1"):
            self.add(
                "Weak Hash Algorithm",
                Severity.low,
                node,
                "MD5/SHA-1 are broken for passwords; use bcrypt or argon2",
            )


def scan_javascript(path: str, source: str) -> list[Vulnerability]:
    root = js_parser(dialect_for(path)).parse(source.encode("utf-8", errors="replace")).root_node
    scanner = _Scanner(path)
    scanner.scan(root)
    return scanner.findings
