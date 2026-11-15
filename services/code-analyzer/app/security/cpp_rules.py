"""Security rules for C and C++: unsafe buffer functions, shell commands, dynamic SQL."""

from tree_sitter import Node

from app.analyzers.treesitter import cpp_parser, snippet, text, walk
from app.security.models import Severity, Vulnerability

_LITERALS = {
    "string_literal",
    "raw_string_literal",
    "concatenated_string",
    "char_literal",
    "number_literal",
    "true",
    "false",
    "null",
    "nullptr",
}
# Copy into a fixed buffer with no length check.
_UNBOUNDED = {"strcpy", "strcat", "sprintf", "vsprintf", "wcscpy", "wcscat", "lstrcpy", "lstrcat"}
_SHELL = {"system", "popen", "_popen", "_wsystem", "WinExec", "ShellExecute", "ShellExecuteA"}
_EXEC = {"execl", "execlp", "execle", "execv", "execvp", "execve"}
_SQL_CALLS = {
    "mysql_query",
    "mysql_real_query",
    "sqlite3_exec",
    "PQexec",
    "exec",
    "execute",
    "executeQuery",
    "executeUpdate",
}
_SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "drop ", "create ", "alter ")
_WEAK_HASHES = {"MD5", "MD5_Init", "SHA1", "SHA1_Init", "EVP_md5", "EVP_sha1", "DES_ecb_encrypt"}


def _call_name(node: Node) -> str:
    function = node.child_by_field_name("function")
    if function is None:
        return ""
    if function.type in ("field_expression", "qualified_identifier"):
        name = function.child_by_field_name("field") or function.child_by_field_name("name")
        return text(name)
    return text(function)


def _arguments(node: Node) -> list[Node]:
    arguments = node.child_by_field_name("arguments")
    return list(arguments.named_children) if arguments is not None else []


def _string(node: Node) -> str | None:
    if node.type == "string_literal":
        return "".join(text(c) for c in node.named_children if c.type == "string_content")
    if node.type == "concatenated_string":
        return "".join(_string(c) or "" for c in node.named_children)
    return None


def _operands(node: Node) -> list[Node]:
    operands, stack = [], [node]
    while stack:
        current = stack.pop()
        operator = current.child_by_field_name("operator")
        if current.type == "parenthesized_expression" and current.named_child_count == 1:
            stack.append(current.named_children[0])
        elif current.type == "binary_expression" and operator is not None and operator.type == "+":
            stack.append(current.child_by_field_name("right"))
            stack.append(current.child_by_field_name("left"))
        else:
            operands.append(current)
    return operands


class _Scanner:
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Vulnerability] = []
        self.dynamic_vars: set[str] = set()  # std::string q = "SELECT..." + name;
        self.sql_vars: set[str] = set()

    def add(self, kind: str, severity: Severity, node: Node, description: str) -> None:
        self.findings.append(
            Vulnerability(
                kind, severity, self.path, node.start_point.row + 1, description, snippet(node)
            )
        )

    def dynamic(self, node: Node) -> bool:
        if node.type == "binary_expression":
            parts = _operands(node)
            return len(parts) > 1 and any(p.type not in _LITERALS for p in parts)
        if node.type == "call_expression" and _call_name(node) == "c_str":
            target = node.child_by_field_name("function")
            argument = target.child_by_field_name("argument") if target is not None else None
            return argument is not None and self.dynamic(argument)
        if node.type == "identifier":
            return text(node) in self.dynamic_vars
        return False

    def sql(self, node: Node) -> bool:
        if node.type == "identifier":
            return text(node) in self.sql_vars
        if node.type == "call_expression" and _call_name(node) == "c_str":
            target = node.child_by_field_name("function")
            argument = target.child_by_field_name("argument") if target is not None else None
            return argument is not None and self.sql(argument)
        return any(
            (_string(p) or "").lstrip().lower().startswith(_SQL_KEYWORDS) for p in _operands(node)
        )

    def remember(self, name: str, value: Node | None, append: bool = False) -> None:
        if value is None:
            return
        if self.dynamic(value) or (append and value.type not in _LITERALS):
            self.dynamic_vars.add(name)
            if self.sql(value) or name in self.sql_vars:
                self.sql_vars.add(name)
        elif self.sql(value):
            self.sql_vars.add(name)
        elif not append:
            self.dynamic_vars.discard(name)
            self.sql_vars.discard(name)

    def scan(self, root: Node) -> None:
        functions = [n for n in walk(root) if n.type == "function_definition"] or [root]
        for function in functions:
            self.dynamic_vars, self.sql_vars = set(), set()
            for node in walk(function):
                self.visit(node)
        unique = {(f.type, f.line, f.evidence): f for f in self.findings}
        self.findings = list(unique.values())

    def visit(self, node: Node) -> None:
        if node.type == "init_declarator":
            self.remember(
                text(node.child_by_field_name("declarator")), node.child_by_field_name("value")
            )
        elif node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            operator = node.child_by_field_name("operator")
            if left is not None and left.type == "identifier":
                self.remember(
                    text(left),
                    node.child_by_field_name("right"),
                    append=operator is not None and operator.type == "+=",
                )
        elif node.type == "call_expression":
            self.call(node)

    def call(self, node: Node) -> None:
        name = _call_name(node)
        args = _arguments(node)
        if name == "gets":
            self.add(
                "Buffer Overflow",
                Severity.critical,
                node,
                "gets() cannot limit the input length; use fgets(buf, sizeof buf, stdin)",
            )
        elif name in _UNBOUNDED and len(args) >= 2 and args[1].type not in _LITERALS:
            self.add(
                "Buffer Overflow",
                Severity.high,
                node,
                f"{name}() copies without a length limit; use snprintf/strncpy or std::string",
            )
        elif name in ("scanf", "sscanf", "fscanf") and any(
            "%s" in (_string(a) or "") for a in args
        ):
            self.add(
                "Buffer Overflow",
                Severity.high,
                node,
                f"{name}() with %s has no width limit; use %99s or std::getline",
            )
        elif name in ("printf", "fprintf") and args:
            fmt = args[0] if name == "printf" else (args[1] if len(args) > 1 else None)
            if (
                fmt is not None
                and fmt.type == "identifier"
                and len(args) == (1 if name == "printf" else 2)
            ):
                self.add(
                    "Format String",
                    Severity.high,
                    node,
                    f'{name}() with a variable as the format; use {name}("%s", value)',
                )
        elif name in _SHELL and args and args[0].type not in _LITERALS:
            self.add(
                "Command Injection",
                Severity.high,
                node,
                f"{name}() runs a shell command built from variables",
            )
        elif name in _EXEC and len(args) > 1 and any(a.type not in _LITERALS for a in args[1:]):
            self.add(
                "Command Injection",
                Severity.medium,
                node,
                f"{name}() with arguments from variables; validate them",
            )
        elif name in _SQL_CALLS:
            query = (
                args[1]
                if name in ("mysql_query", "mysql_real_query", "sqlite3_exec", "PQexec")
                and len(args) > 1
                else (args[0] if args else None)
            )
            if (
                query is not None
                and self.dynamic(query)
                and (self.sql(query) or name.startswith(("mysql", "sqlite3", "PQ")))
            ):
                self.add(
                    "SQL Injection",
                    Severity.critical,
                    node,
                    f"{name}() runs SQL built from variables; use prepared statements",
                )
        elif name in _WEAK_HASHES:
            self.add(
                "Weak Hash Algorithm",
                Severity.medium,
                node,
                f"{name} is broken for passwords; use a slow hash (bcrypt/argon2)",
            )


def scan_cpp(path: str, source: str) -> list[Vulnerability]:
    root = cpp_parser().parse(source.encode("utf-8", errors="replace")).root_node
    scanner = _Scanner(path)
    scanner.scan(root)
    return scanner.findings
