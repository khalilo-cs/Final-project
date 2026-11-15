"""Security rules for C# (ADO.NET, Entity Framework, Dapper, ASP.NET, WinForms)."""

from tree_sitter import Node

from app.analyzers.csharp_analyzer import METHOD_TYPES
from app.analyzers.treesitter import csharp_parser, snippet, text, walk
from app.security.models import Severity, Vulnerability

_SQL_COMMANDS = {
    "SqlCommand",
    "MySqlCommand",
    "OleDbCommand",
    "OdbcCommand",
    "SQLiteCommand",
    "SqliteCommand",
    "NpgsqlCommand",
    "OracleCommand",
    "SqlDataAdapter",
    "MySqlDataAdapter",
    "OleDbDataAdapter",
    "SQLiteDataAdapter",
    "NpgsqlDataAdapter",
}
_SQL_METHODS = {
    "ExecuteSqlRaw",
    "ExecuteSqlCommand",
    "FromSqlRaw",
    "SqlQuery",
    "ExecuteQuery",
    "ExecuteSqlRawAsync",
    "Query",
    "QueryAsync",
    "QueryFirst",
    "QueryFirstOrDefault",
    "QuerySingle",
    "Execute",
    "ExecuteAsync",
    "ExecuteScalar",
}
_SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "drop ", "create ", "alter ", "exec ")
_STRINGS = {"string_literal", "verbatim_string_literal", "raw_string_literal", "character_literal"}
_FORMATTERS = {
    "BinaryFormatter",
    "SoapFormatter",
    "NetDataContractSerializer",
    "LosFormatter",
    "ObjectStateFormatter",
}
_WEAK_TYPES = {
    "MD5",
    "SHA1",
    "MD5CryptoServiceProvider",
    "SHA1CryptoServiceProvider",
    "SHA1Managed",
    "DES",
    "DESCryptoServiceProvider",
    "RC2",
    "TripleDES",
}
_LITERALS = _STRINGS | {"integer_literal", "real_literal", "boolean_literal", "null_literal"}


def _string_text(node: Node) -> str:
    if node.type in _STRINGS:
        return text(node).lstrip("@$\"'").lower()
    if node.type == "interpolated_string_expression":
        return "".join(text(c) for c in node.named_children if c.type == "string_content").lower()
    return ""


def _operands(node: Node) -> list[Node]:
    """Flatten `a + b + c` without recursion."""
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


def _call_name(node: Node) -> tuple[str, str]:
    """(target, method) for x.Y(...) / Y(...)."""
    function = node.child_by_field_name("function")
    if function is None:
        return "", ""
    if function.type == "member_access_expression":
        return text(function.child_by_field_name("expression")), text(
            function.child_by_field_name("name")
        )
    return "", text(function)


def _arguments(node: Node) -> list[Node]:
    arguments = node.child_by_field_name("arguments")
    if arguments is None:
        arguments = next((c for c in node.children if c.type == "argument_list"), None)
    if arguments is None:
        return []
    return [a.named_children[-1] for a in arguments.named_children if a.named_child_count]


def _value(declarator: Node) -> Node | None:
    named = declarator.named_children
    return named[-1] if len(named) > 1 else None


class _Scanner:
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Vulnerability] = []
        self.sql_vars: set[str] = set()
        self.dynamic_vars: set[str] = set()
        self.sql_literals: set[str] = set()

    def add(self, kind: str, severity: Severity, node: Node, description: str) -> None:
        self.findings.append(
            Vulnerability(
                kind, severity, self.path, node.start_point.row + 1, description, snippet(node)
            )
        )

    # -- what counts as "built from input" ------------------------------------------------

    def dynamic(self, node: Node) -> bool:
        if node.type == "interpolated_string_expression":
            return any(c.type == "interpolation" for c in node.named_children)
        if node.type == "binary_expression":
            parts = _operands(node)
            return len(parts) > 1 and any(p.type not in _LITERALS for p in parts)
        if node.type == "invocation_expression":
            target, name = _call_name(node)
            return (
                target in ("string", "String")
                and name in ("Format", "Concat", "Join")
                and len(_arguments(node)) > 1
            )
        if node.type == "identifier":
            return text(node) in self.dynamic_vars
        return False

    def sql_text(self, node: Node) -> bool:
        """The expression looks like SQL (a SQL literal, or a variable holding one)."""
        if node.type == "invocation_expression":
            candidates = _arguments(node)[:1]
        elif node.type == "binary_expression":
            candidates = _operands(node)
        else:
            candidates = [node]
        sql_names = self.sql_vars | self.sql_literals
        return any(
            _string_text(c).lstrip().startswith(_SQL_KEYWORDS)
            or (c.type == "identifier" and text(c) in sql_names)
            for c in candidates
        )

    def dynamic_sql(self, node: Node) -> bool:
        if node.type == "identifier":
            return text(node) in self.sql_vars or text(node) in self.dynamic_vars
        return self.dynamic(node)

    def remember(self, name: str, value: Node, append: bool = False) -> None:
        sqlish = self.sql_text(value)
        if append:
            # q += txtName.Text  /  q += " WHERE id=" + id
            if value.type not in _LITERALS or self.dynamic(value):
                self.dynamic_vars.add(name)
                if sqlish or name in self.sql_vars or name in self.sql_literals:
                    self.sql_vars.add(name)
            elif sqlish and name not in self.dynamic_vars:
                self.sql_literals.add(name)
            return
        dynamic = self.dynamic(value)
        for names, keep in (
            (self.dynamic_vars, dynamic),
            (self.sql_vars, dynamic and sqlish),
            (self.sql_literals, not dynamic and sqlish),
        ):
            if keep:
                names.add(name)
            else:
                names.discard(name)

    # -- scanning -----------------------------------------------------------------------

    def scan(self, root: Node) -> None:
        methods = [n for n in walk(root) if n.type in METHOD_TYPES] or [root]
        for method in methods:
            self.sql_vars, self.dynamic_vars, self.sql_literals = set(), set(), set()
            for node in walk(method):
                self.visit(node)
        self.top_level(root)
        # Methods nested in methods are visited twice; keep one finding per spot.
        unique = {(f.type, f.line, f.evidence): f for f in self.findings}
        self.findings = list(unique.values())

    def visit(self, node: Node) -> None:
        kind = node.type
        if kind == "variable_declarator" and (value := _value(node)) is not None:
            self.remember(text(node.named_children[0]), value)
        elif kind == "assignment_expression":
            self.assignment(node)
        elif kind == "object_creation_expression":
            self.creation(node)
        elif kind == "invocation_expression":
            self.invocation(node)

    def assignment(self, node: Node) -> None:
        left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
        operator = node.child_by_field_name("operator")
        if left is None or right is None:
            return
        if left.type == "identifier":
            self.remember(text(left), right, append=operator is not None and operator.type == "+=")
            return
        member = (
            text(left.child_by_field_name("name"))
            if left.type == "member_access_expression"
            else ""
        )
        if member == "CommandText" and self.dynamic_sql(right):
            self.add(
                "SQL Injection",
                Severity.critical,
                node,
                "CommandText is built from variables; use SqlParameter "
                "(cmd.Parameters.AddWithValue)",
            )
        elif member in ("Arguments", "FileName") and self.dynamic(right):
            self.add(
                "Command Injection",
                Severity.high,
                node,
                f"Process {member} is built from variables; validate it against an allow-list",
            )
        elif member == "ServerCertificateValidationCallback" and text(right).replace(
            " ", ""
        ).endswith("=>true"):
            self.add(
                "Disabled TLS Verification",
                Severity.high,
                node,
                "Every TLS certificate is accepted; remove the callback",
            )

    def creation(self, node: Node) -> None:
        type_name = text(node.child_by_field_name("type")).rsplit(".", 1)[-1]
        args = _arguments(node)
        if type_name in _SQL_COMMANDS and args and self.dynamic_sql(args[0]):
            self.add(
                "SQL Injection",
                Severity.critical,
                node,
                f"{type_name} receives SQL built by concatenation; use parameters "
                "(@name with cmd.Parameters.AddWithValue)",
            )
        elif type_name in _FORMATTERS:
            self.add(
                "Insecure Deserialization",
                Severity.high,
                node,
                f"{type_name} can run attacker code when deserializing; use System.Text.Json",
            )
        elif type_name == "ProcessStartInfo" and any(self.dynamic(a) for a in args):
            self.add(
                "Command Injection",
                Severity.high,
                node,
                "Process arguments are built from variables",
            )
        elif type_name in _WEAK_TYPES:
            self.weak(node, type_name)

    def invocation(self, node: Node) -> None:
        target, name = _call_name(node)
        args = _arguments(node)
        if (
            name in _SQL_METHODS
            and args
            and self.dynamic_sql(args[0])
            and (
                name not in ("Query", "QueryAsync", "Execute", "ExecuteAsync", "ExecuteScalar")
                or self.sql_text(args[0])
            )
        ):
            self.add(
                "SQL Injection",
                Severity.critical,
                node,
                f"{name}() runs SQL built from variables; pass parameters instead",
            )
        elif target == "Process" and name == "Start" and any(self.dynamic(a) for a in args):
            self.add(
                "Command Injection",
                Severity.high,
                node,
                "Process.Start() with arguments built from variables",
            )
        elif target.rsplit(".", 1)[-1] in _WEAK_TYPES and name == "Create":
            self.weak(node, target)
        elif (
            target == "Response"
            and name == "Write"
            and args
            and (self.dynamic(args[0]) or "Request" in text(args[0]))
        ):
            self.add(
                "Cross-Site Scripting (XSS)",
                Severity.medium,
                node,
                "Response.Write() of unencoded input; use HttpUtility.HtmlEncode",
            )
        elif target == "Html" and name == "Raw" and args and args[0].type not in _STRINGS:
            self.add(
                "Cross-Site Scripting (XSS)",
                Severity.medium,
                node,
                "Html.Raw() disables encoding for this value",
            )

    def weak(self, node: Node, name: str) -> None:
        if name.upper().startswith(("MD5", "SHA1")):
            self.add(
                "Weak Hash Algorithm",
                Severity.medium,
                node,
                f"{name} is broken for passwords; use PBKDF2 (Rfc2898DeriveBytes) or BCrypt",
            )
        else:
            self.add(
                "Weak Cryptography", Severity.medium, node, f"{name} is a weak cipher; use Aes"
            )

    def top_level(self, root: Node) -> None:
        for node in walk(root):
            if node.type == "attribute" and text(node).replace(" ", "") == "ValidateInput(false)":
                self.add(
                    "Cross-Site Scripting (XSS)",
                    Severity.medium,
                    node,
                    "Request validation is disabled for this action",
                )
            elif node.type == "member_access_expression" and text(node) in (
                "TypeNameHandling.All",
                "TypeNameHandling.Auto",
                "TypeNameHandling.Objects",
            ):
                self.add(
                    "Insecure Deserialization",
                    Severity.high,
                    node,
                    "Json.NET TypeNameHandling lets the JSON choose the type to create",
                )
            elif node.type == "member_access_expression" and text(node) == "CipherMode.ECB":
                self.add(
                    "Weak Cryptography",
                    Severity.medium,
                    node,
                    "ECB mode leaks patterns in the data; use CBC/GCM with a random IV",
                )


def scan_csharp(path: str, source: str) -> list[Vulnerability]:
    root = csharp_parser().parse(source.encode("utf-8", errors="replace")).root_node
    scanner = _Scanner(path)
    scanner.scan(root)
    return scanner.findings
