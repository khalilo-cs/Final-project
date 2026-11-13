"""AST-based security rules for Python source."""

import ast

from app.security.models import Severity, Vulnerability

_SQL_METHODS = {"execute", "executemany", "executescript", "raw"}
_SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "drop ", "create ", "alter ")
_SHELL_FUNCS = {"os.system", "os.popen", "commands.getoutput", "commands.getstatusoutput"}
_SUBPROCESS_FUNCS = {"run", "call", "Popen", "check_output", "check_call", "getoutput"}
_UNSAFE_LOADERS = {
    "pickle.load",
    "pickle.loads",
    "cPickle.load",
    "cPickle.loads",
    "marshal.load",
    "marshal.loads",
    "shelve.open",
    "dill.load",
    "dill.loads",
}
_WEAK_HASHES = {"hashlib.md5", "hashlib.sha1"}


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_dynamic_string(node: ast.AST) -> bool:
    """True when a string is assembled from non-constant parts."""
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(value, ast.FormattedValue) for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        sides = (node.left, node.right)
        has_text = any(_has_string(side) for side in sides)
        return has_text and not all(isinstance(side, ast.Constant) for side in sides)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "format" and _has_string(node.func.value)
    return False


def _has_string(node: ast.AST) -> bool:
    return any(
        isinstance(sub, ast.Constant) and isinstance(sub.value, str) for sub in ast.walk(node)
    )


def _looks_like_sql(node: ast.AST) -> bool:
    return any(
        isinstance(sub, ast.Constant)
        and isinstance(sub.value, str)
        and sub.value.lstrip().lower().startswith(_SQL_KEYWORDS)
        for sub in ast.walk(node)
    )


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _is_true(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


class _Scanner(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Vulnerability] = []
        # Variables holding SQL text built from dynamic parts, per function scope.
        self.tainted_sql: list[set[str]] = [set()]

    def _add(self, kind: str, severity: Severity, node: ast.AST, description: str) -> None:
        self.findings.append(
            Vulnerability(kind, severity, self.path, node.lineno, description, _snippet(node))
        )

    def _scoped(self, node: ast.AST) -> None:
        self.tainted_sql.append(set())
        self.generic_visit(node)
        self.tainted_sql.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _scoped

    def visit_Assign(self, node: ast.Assign) -> None:
        if _is_dynamic_string(node.value) and _looks_like_sql(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.tainted_sql[-1].add(target.id)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        # query += " WHERE id = " + user_id
        if (
            isinstance(node.target, ast.Name)
            and isinstance(node.op, ast.Add)
            and not isinstance(node.value, ast.Constant)
            and node.target.id.lower() in ("query", "sql", "stmt", "statement")
        ):
            self.tainted_sql[-1].add(node.target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        first = node.args[0] if node.args else None
        self._check_sql(node, first)
        self._check_command(node, name, first)
        self._check_misc(node, name, first)
        self.generic_visit(node)

    def _check_sql(self, node: ast.Call, first: ast.AST | None) -> None:
        if not (isinstance(node.func, ast.Attribute) and node.func.attr in _SQL_METHODS):
            return
        if first is None:
            return
        # sqlalchemy.text("... " + x) wraps the string: look inside the wrapper.
        if isinstance(first, ast.Call) and _dotted(first.func).endswith("text") and first.args:
            first = first.args[0]
        tainted = isinstance(first, ast.Name) and first.id in self.tainted_sql[-1]
        if tainted or _is_dynamic_string(first):
            self._add(
                "SQL Injection",
                Severity.critical,
                node,
                "SQL query is built with string formatting/concatenation; "
                "use parameterized queries instead",
            )

    def _check_command(self, node: ast.Call, name: str, first: ast.AST | None) -> None:
        dynamic = first is not None and not isinstance(first, ast.Constant)
        if name in _SHELL_FUNCS and dynamic:
            self._add(
                "Command Injection",
                Severity.critical,
                node,
                f"{name}() runs a shell command built from variable input",
            )
        elif (
            name.startswith("subprocess.")
            and name.split(".")[-1] in _SUBPROCESS_FUNCS
            and _is_true(_keyword(node, "shell"))
            and dynamic
        ):
            self._add(
                "Command Injection",
                Severity.critical,
                node,
                "subprocess call with shell=True and a non-constant command",
            )
        elif name in ("eval", "exec") and dynamic:
            self._add(
                "Code Injection",
                Severity.high,
                node,
                f"{name}() executes dynamically built code",
            )

    def _check_misc(self, node: ast.Call, name: str, first: ast.AST | None) -> None:
        if name in _UNSAFE_LOADERS:
            self._add(
                "Insecure Deserialization",
                Severity.high,
                node,
                f"{name}() can execute arbitrary code when the data is untrusted",
            )
        elif name in ("yaml.load", "yaml.load_all"):
            loader = _keyword(node, "Loader") or (node.args[1] if len(node.args) > 1 else None)
            if loader is None or "safe" not in _dotted(loader).lower():
                self._add(
                    "Insecure Deserialization",
                    Severity.high,
                    node,
                    "yaml.load() without SafeLoader; use yaml.safe_load()",
                )
        elif name.startswith(("requests.", "httpx.")) and _is_false(_keyword(node, "verify")):
            self._add(
                "Disabled TLS Verification",
                Severity.medium,
                node,
                "TLS certificate verification is disabled (verify=False)",
            )
        elif name.endswith(".run") and _is_true(_keyword(node, "debug")):
            self._add(
                "Debug Mode Enabled",
                Severity.medium,
                node,
                "Application started with debug=True; the debugger allows code execution",
            )
        elif name in _WEAK_HASHES:
            self._add(
                "Weak Hash Algorithm",
                Severity.low,
                node,
                f"{name} is broken for security purposes (never use it for passwords)",
            )


def _is_false(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _snippet(node: ast.AST) -> str:
    text = ast.unparse(node)
    return text if len(text) <= 160 else text[:157] + "..."


def scan_python(path: str, source: str) -> list[Vulnerability]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return []
    scanner = _Scanner(path)
    scanner.visit(tree)
    return scanner.findings
