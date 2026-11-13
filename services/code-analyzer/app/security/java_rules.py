"""Security rules for Java source (servlets, JDBC, JPA, Spring JdbcTemplate)."""

from tree_sitter import Node

from app.analyzers.java_analyzer import METHOD_TYPES
from app.analyzers.treesitter import java_parser, snippet, text, walk
from app.security.models import Severity, Vulnerability

_SQL_SINKS = {
    "executeQuery", "executeUpdate", "executeLargeUpdate", "execute", "addBatch",
    "prepareStatement", "prepareCall", "createQuery", "createNativeQuery", "createSQLQuery",
    "query", "queryForList", "queryForObject", "queryForMap", "update", "batchUpdate",
}  # fmt: skip
_SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "drop ", "create ", "alter ")
_SQL_VARIABLE_NAMES = {"query", "sql", "stmt", "statement", "q"}
_REQUEST_SOURCES = {"getParameter", "getParameterValues", "getHeader", "getQueryString"}
_FILE_TYPES = {"File", "FileInputStream", "FileOutputStream", "FileReader", "FileWriter"}
_WRITE_METHODS = {"print", "println", "write", "append", "printf", "format"}
_SHELLS = {"sh", "bash", "/bin/sh", "/bin/bash", "cmd", "cmd.exe", "powershell"}
_WEAK_DIGESTS = {"md5", "md2", "sha1", "sha-1"}
_LITERALS = {
    "string_literal", "decimal_integer_literal", "hex_integer_literal", "decimal_floating_point_literal",
    "character_literal", "true", "false", "null_literal", "text_block",
}  # fmt: skip


def _string_value(node: Node) -> str | None:
    if node.type != "string_literal":
        return None
    return "".join(text(c) for c in node.named_children if c.type == "string_fragment")


def _concat_operands(node: Node) -> list[Node]:
    """Flatten `a + b + c` into [a, b, c] without recursion."""
    operands, stack = [], [node]
    while stack:
        current = stack.pop()
        if current.type == "parenthesized_expression" and current.named_child_count == 1:
            stack.append(current.named_children[0])
        elif current.type == "binary_expression" and _operator(current) == "+":
            stack.append(current.child_by_field_name("right"))
            stack.append(current.child_by_field_name("left"))
        else:
            operands.append(current)
    return operands


def _operator(node: Node) -> str | None:
    operator = node.child_by_field_name("operator")
    return operator.type if operator is not None else None


def _is_sql_text(value: str | None) -> bool:
    return value is not None and value.lstrip().lower().startswith(_SQL_KEYWORDS)


def _arguments(node: Node) -> list[Node]:
    arguments = node.child_by_field_name("arguments")
    return list(arguments.named_children) if arguments is not None else []


def _method(node: Node) -> str:
    return text(node.child_by_field_name("name"))


class _Scanner:
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Vulnerability] = []
        self.sql_vars: set[str] = set()  # locals holding dynamically built SQL
        self.request_vars: set[str] = set()  # locals holding request input
        self.writer_vars: set[str] = set()  # locals holding response.getWriter()

    def add(self, kind: str, severity: Severity, node: Node, description: str) -> None:
        self.findings.append(
            Vulnerability(
                kind, severity, self.path, node.start_point.row + 1, description, snippet(node)
            )
        )

    # -- taint helpers -------------------------------------------------------------------

    def dynamic_sql(self, node: Node) -> bool:
        """SQL text assembled from non-constant parts."""
        if node.type == "binary_expression" and _operator(node) == "+":
            operands = _concat_operands(node)
            has_sql = any(_is_sql_text(_string_value(o)) for o in operands) or any(
                o.type == "identifier" and text(o) in self.sql_vars for o in operands
            )
            return has_sql and any(o.type not in _LITERALS for o in operands)
        if node.type == "method_invocation":
            name, target = _method(node), node.child_by_field_name("object")
            args = _arguments(node)
            if name == "format" and text(target) == "String" and args:
                return _is_sql_text(_string_value(args[0])) and len(args) > 1
            if name == "formatted" and target is not None:
                return _is_sql_text(_string_value(target)) and bool(args)
        return node.type == "identifier" and text(node) in self.sql_vars

    def from_request(self, node: Node) -> bool:
        for sub in walk(node):
            if sub.type == "method_invocation" and _method(sub) in _REQUEST_SOURCES:
                return True
            if sub.type == "identifier" and text(sub) in self.request_vars:
                return True
        return False

    def track(self, name: str, value: Node | None) -> None:
        if value is None:
            return
        if self.dynamic_sql(value):
            self.sql_vars.add(name)
        if self.from_request(value):
            self.request_vars.add(name)
        if "getWriter()" in text(value) or "getOutputStream()" in text(value):
            self.writer_vars.add(name)

    # -- main walk -----------------------------------------------------------------------

    def scan(self, root: Node) -> None:
        for node in walk(root):
            kind = node.type
            if kind in METHOD_TYPES:
                self.sql_vars, self.request_vars, self.writer_vars = set(), set(), set()
            elif kind == "variable_declarator":
                self.track(
                    text(node.child_by_field_name("name")), node.child_by_field_name("value")
                )
            elif kind == "assignment_expression":
                self.assignment(node)
            elif kind == "method_invocation":
                self.invocation(node)
            elif kind == "object_creation_expression":
                self.creation(node)

    def assignment(self, node: Node) -> None:
        left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
        if left is None or left.type != "identifier" or right is None:
            return
        name = text(left)
        if _operator(node) == "+=":
            if right.type not in _LITERALS and (
                name in self.sql_vars or name.lower() in _SQL_VARIABLE_NAMES
            ):
                self.sql_vars.add(name)
            if self.from_request(right):
                self.request_vars.add(name)
        else:
            self.track(name, right)

    def invocation(self, node: Node) -> None:
        name, target, args = _method(node), node.child_by_field_name("object"), _arguments(node)
        target_text = text(target)

        if name in _SQL_SINKS and args and self.dynamic_sql(args[0]):
            self.add(
                "SQL Injection",
                Severity.critical,
                node,
                "SQL query is built by string concatenation/formatting; "
                "use PreparedStatement with ? placeholders",
            )
        elif name == "exec" and "Runtime" in target_text and args:
            if args[0].type not in _LITERALS:
                self.add(
                    "Command Injection",
                    Severity.critical,
                    node,
                    "Runtime.exec() runs a command built from variable input",
                )
        elif name in _WRITE_METHODS and (
            "getWriter()" in target_text or target_text in self.writer_vars
        ):
            if any(self.from_request(arg) for arg in args):
                self.add(
                    "Cross-Site Scripting (XSS)",
                    Severity.high,
                    node,
                    "Request input is written to the HTTP response without encoding",
                )
        elif name in ("get", "of") and target_text in ("Paths", "Path"):
            if any(self.from_request(arg) for arg in args):
                self.path_traversal(node)
        elif name == "getInstance" and target_text in ("MessageDigest", "Cipher") and args:
            self.crypto(node, target_text, (_string_value(args[0]) or "").lower())

    def creation(self, node: Node) -> None:
        type_name = text(node.child_by_field_name("type")).split("<")[0].split(".")[-1]
        args = _arguments(node)
        if type_name in ("ObjectInputStream", "XMLDecoder"):
            self.add(
                "Insecure Deserialization",
                Severity.high,
                node,
                f"{type_name} can execute arbitrary code when the data is untrusted",
            )
        elif type_name in _FILE_TYPES and any(self.from_request(arg) for arg in args):
            self.path_traversal(node)
        elif type_name == "ProcessBuilder":
            values = [_string_value(arg) for arg in args]
            uses_shell = any(v is not None and v.lower() in _SHELLS for v in values)
            if uses_shell and any(arg.type not in _LITERALS for arg in args):
                self.add(
                    "Command Injection",
                    Severity.critical,
                    node,
                    "ProcessBuilder runs a shell with a variable command",
                )

    def path_traversal(self, node: Node) -> None:
        self.add(
            "Path Traversal",
            Severity.high,
            node,
            "File path is built from request input; validate it against a base directory",
        )

    def crypto(self, node: Node, target: str, algorithm: str) -> None:
        if target == "MessageDigest" and algorithm in _WEAK_DIGESTS:
            self.add(
                "Weak Hash Algorithm",
                Severity.low,
                node,
                f"{algorithm.upper()} is broken for security purposes (never use it for passwords)",
            )
        elif target == "Cipher" and (
            algorithm.startswith(("des", "rc4", "rc2", "blowfish"))
            or "/ecb" in algorithm
            or algorithm == "aes"  # defaults to AES/ECB
        ):
            self.add(
                "Weak Cryptography",
                Severity.medium,
                node,
                f"Cipher '{algorithm}' is insecure; use AES/GCM/NoPadding",
            )


def scan_java(path: str, source: str) -> list[Vulnerability]:
    tree = java_parser().parse(source.encode("utf-8", errors="replace"))
    scanner = _Scanner(path)
    scanner.scan(tree.root_node)
    return scanner.findings
