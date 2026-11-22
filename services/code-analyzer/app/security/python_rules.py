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
# File APIs that must never receive a raw user-supplied path.
_FILE_SINKS = {
    "open",
    "send_file",
    "send_from_directory_unsafe",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "shutil.rmtree",
    "shutil.copy",
    "shutil.move",
    "os.open",
    "io.open",
    "FileResponse",
    "Path",
    "pathlib.Path",
}
_PATH_SAFE = {
    "secure_filename", "os.path.basename", "basename", "safe_join",
    "werkzeug.utils.secure_filename",
}  # fmt: skip
# Reading these means the value came straight from the HTTP request.
_REQUEST_ROOTS = ("request.args", "request.form", "request.values", "request.json",
                  "request.get_json", "request.files", "request.GET", "request.POST",
                  "request.data", "request.cookies", "request.query_params")  # fmt: skip
_VALIDATORS = ("validate", "is_valid", "isdigit", "isnumeric", "isalnum", "fullmatch", "match",
               "int", "float", "len", "isinstance", "schema", "load", "parse_obj",
               "model_validate", "secure_filename", "clean")  # fmt: skip


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
        # Variables holding raw request input, per function scope.
        self.from_request: list[set[str]] = [set()]
        self.request_reads: list[list[ast.AST]] = [[]]
        self.validated: list[bool] = [False]

    def _add(self, kind: str, severity: Severity, node: ast.AST, description: str) -> None:
        self.findings.append(
            Vulnerability(kind, severity, self.path, node.lineno, description, _snippet(node))
        )

    def _scoped(self, node: ast.AST) -> None:
        self.tainted_sql.append(set())
        self.from_request.append(set())
        self.request_reads.append([])
        self.validated.append(False)
        self.generic_visit(node)
        self.tainted_sql.pop()
        self.from_request.pop()
        reads = self.request_reads.pop()
        validated = self.validated.pop()
        if reads and not validated:
            self._add(
                "Missing Input Validation",
                Severity.medium,
                reads[0],
                "Request input is used without any validation (type, length, format or range)",
            )

    def _is_request(self, node: ast.AST) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute | ast.Call | ast.Subscript):
                target = sub.func if isinstance(sub, ast.Call) else sub
                if isinstance(target, ast.Subscript):
                    target = target.value
                if _dotted(target).startswith(_REQUEST_ROOTS):
                    return True
            if isinstance(sub, ast.Name) and sub.id in self.from_request[-1]:
                return True
        return False

    def _reads_request(self, node: ast.AST) -> bool:
        saved = self.from_request[-1]
        self.from_request[-1] = set()
        try:
            return self._is_request(node)
        finally:
            self.from_request[-1] = saved

    visit_FunctionDef = visit_AsyncFunctionDef = _scoped

    def visit_If(self, node: ast.If) -> None:
        if self._is_request(node.test):
            self.validated[-1] = True
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        if node.handlers:
            self.validated[-1] = True
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._is_request(node.value) and not _sanitized(node.value):
            if not any(isinstance(n, ast.Name) and n.id in self.from_request[-1]
                       for n in ast.walk(node.value)):  # fmt: skip
                self.request_reads[-1].append(node)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.from_request[-1].add(target.id)
        elif _sanitized(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.from_request[-1].discard(target.id)
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
        self._check_path(node, name)
        if name.split(".")[-1] in _VALIDATORS and any(self._is_request(a) for a in node.args):
            self.validated[-1] = True
        elif any(self._reads_request(a) for a in [*node.args, *(k.value for k in node.keywords)]):
            self.request_reads[-1].append(node)
        self.generic_visit(node)

    def _check_path(self, node: ast.Call, name: str) -> None:
        if name not in _FILE_SINKS:
            return
        if any(self._is_request(arg) and not _sanitized(arg) for arg in node.args):
            self._add(
                "Path Traversal",
                Severity.high,
                node,
                f"{name}() receives a path taken from the request; use "
                "secure_filename()/basename and check it stays inside the upload folder",
            )

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


def _sanitized(node: ast.AST) -> bool:
    return any(
        isinstance(sub, ast.Call) and _dotted(sub.func) in _PATH_SAFE | {"int", "float"}
        for sub in ast.walk(node)
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
