"""Web-application rules that the per-language AST scanners do not cover.

Line-oriented heuristics shared by every language a student project may use:

* CSRF: protection explicitly disabled, or cookie/form-based handlers with no
  anti-forgery token anywhere in the file.
* Path Traversal: file APIs fed straight from request input (C#, PHP).
* Missing Input Validation: request input used without any validation call.
* PHP: the classic injections ($_GET/$_POST into SQL, shell, include, echo).

Python path traversal and input validation are handled on the AST in
python_rules; this module only adds the Flask/Django CSRF checks for Python.
"""

import ast
import re

from app.security.models import Severity, Vulnerability

_LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".java": "java",
    ".cs": "csharp",
    ".php": "php",
}


def _ext(path: str) -> str:
    dot = path.rfind(".")
    return path[dot:].lower() if dot != -1 else ""


def _strip_comment(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith(("//", "#", "*", "/*")):
        return ""
    return line


class _Collector:
    def __init__(self, path: str, lines: list[str]) -> None:
        self.path = path
        self.lines = lines
        self.findings: list[Vulnerability] = []
        self._seen: set[tuple[str, int]] = set()

    def add(self, kind: str, severity: Severity, line: int, description: str) -> None:
        if (kind, line) in self._seen:
            return
        self._seen.add((kind, line))
        evidence = self.lines[line - 1].strip()[:160] if 0 < line <= len(self.lines) else ""
        self.findings.append(Vulnerability(kind, severity, self.path, line, description, evidence))

    def each(self, pattern: re.Pattern):
        for number, raw in enumerate(self.lines, start=1):
            line = _strip_comment(raw)
            if line and pattern.search(line):
                yield number, line


# --------------------------------------------------------------------------- CSRF

_CSRF_WORD = re.compile(r"csrf|xsrf|antiforgery|anti-forgery|requestverificationtoken", re.I)

_PY_FORM_POST = re.compile(r"""@\w+\.(route|post)\(.*methods\s*=\s*\[[^\]]*["'](POST|PUT|DELETE)""")
_PY_FORM_READ = re.compile(r"request\.form\b")
_DJANGO_EXEMPT = re.compile(r"@csrf_exempt\b")
_DJANGO_MIDDLEWARE = re.compile(r"^\s*MIDDLEWARE\s*=")

_JS_ROUTE = re.compile(r"\b(app|router)\.(post|put|patch|delete)\s*\(")
_JS_COOKIE_SESSION = re.compile(r"express-session|cookie-session|cookie-parser|urlencoded\s*\(")

_JAVA_DISABLED = re.compile(
    r"csrf\(\)\s*\.disable\(\)|csrf\(\s*\w+\s*->\s*\w+\.disable\(\)\s*\)|"
    r"csrf\(\s*AbstractHttpConfigurer::disable\s*\)|csrf\(\s*Customizer\.disable"
)

_CS_IGNORE = re.compile(r"\[\s*IgnoreAntiforgeryToken")
_CS_POST = re.compile(r"\[\s*Http(Post|Put|Delete)\b")
_CS_VALIDATE = re.compile(r"ValidateAntiForgeryToken|AutoValidateAntiforgeryToken")
_CS_API = re.compile(r"\[\s*ApiController\b")

_PHP_POST = re.compile(r"\$_SERVER\[\s*['\"]REQUEST_METHOD['\"]\s*\]\s*===?\s*['\"]POST|\$_POST\[")


def _csrf(c: _Collector, language: str, source: str) -> None:
    has_token = bool(_CSRF_WORD.search(source))
    if language == "python":
        for line, _ in c.each(_DJANGO_EXEMPT):
            c.add(
                "CSRF",
                Severity.medium,
                line,
                "@csrf_exempt turns off Django's CSRF protection for this view",
            )
        for line, _ in c.each(_DJANGO_MIDDLEWARE):
            block = "\n".join(c.lines[line - 1 : line + 30])
            end = block.find("]")
            if "CsrfViewMiddleware" not in (block[:end] if end != -1 else block):
                c.add(
                    "CSRF",
                    Severity.high,
                    line,
                    "Django MIDDLEWARE does not include CsrfViewMiddleware",
                )
        if not has_token and _PY_FORM_READ.search(source):
            for line, _ in c.each(_PY_FORM_POST):
                c.add(
                    "CSRF",
                    Severity.medium,
                    line,
                    "Form POST handler without CSRF protection (Flask-WTF CSRFProtect)",
                )
    elif language == "javascript":
        if not has_token and _JS_COOKIE_SESSION.search(source):
            for line, _ in c.each(_JS_ROUTE):
                c.add(
                    "CSRF",
                    Severity.medium,
                    line,
                    "State-changing route in a cookie/session app with no CSRF token",
                )
    elif language == "java":
        for line, _ in c.each(_JAVA_DISABLED):
            c.add("CSRF", Severity.high, line, "Spring Security CSRF protection is disabled")
    elif language == "csharp":
        for line, _ in c.each(_CS_IGNORE):
            c.add(
                "CSRF",
                Severity.medium,
                line,
                "[IgnoreAntiforgeryToken] disables anti-forgery validation",
            )
        if not _CS_VALIDATE.search(source) and not _CS_API.search(source):
            for line, _ in c.each(_CS_POST):
                c.add(
                    "CSRF",
                    Severity.medium,
                    line,
                    "MVC POST action without [ValidateAntiForgeryToken]",
                )
    elif language == "php" and not has_token and "session_start" in source:
        for line, _ in c.each(_PHP_POST):
            c.add(
                "CSRF",
                Severity.medium,
                line,
                "Session-based form handler without a CSRF token check",
            )
            break


# ---------------------------------------------------------- PHP injections

_PHP_INPUT = r"\$_(GET|POST|REQUEST|COOKIE|FILES)\b"
_PHP_RULES = [
    (
        re.compile(
            r"\b(mysqli_query|mysql_query|pg_query)\s*\(.*"
            + _PHP_INPUT
            + r"|->\s*(query|exec)\s*\(\s*[\"'].*"
            + _PHP_INPUT
        ),
        "SQL Injection",
        Severity.critical,
        "SQL query built from request input; use prepared statements",
    ),
    (
        re.compile(r"\b(system|exec|shell_exec|passthru|popen|proc_open)\s*\(.*" + _PHP_INPUT),
        "Command Injection",
        Severity.critical,
        "Shell command built from request input",
    ),
    (
        re.compile(r"\b(include|require|include_once|require_once)\b.*" + _PHP_INPUT),
        "Path Traversal",
        Severity.critical,
        "File inclusion path comes from request input (LFI/RFI)",
    ),
    (
        re.compile(
            r"\b(file_get_contents|fopen|readfile|unlink|file_put_contents|file)\s*\(.*"
            + _PHP_INPUT
        ),
        "Path Traversal",
        Severity.high,
        "File path comes from request input without sanitizing",
    ),
    (
        re.compile(r"\b(echo|print)\b[^;]*" + _PHP_INPUT),
        "Cross-Site Scripting (XSS)",
        Severity.high,
        "Request input echoed without htmlspecialchars()",
    ),
    (
        re.compile(r"\bunserialize\s*\(.*" + _PHP_INPUT),
        "Insecure Deserialization",
        Severity.high,
        "unserialize() on request input",
    ),
    (
        re.compile(r"\beval\s*\("),
        "Code Injection",
        Severity.high,
        "eval() executes dynamically built code",
    ),
]
_PHP_SANITIZED = re.compile(
    r"htmlspecialchars|htmlentities|intval|\(int\)|escapeshellarg|"
    r"basename\("
)


def _php(c: _Collector) -> None:
    for pattern, kind, severity, description in _PHP_RULES:
        for line, text in c.each(pattern):
            escaped = _PHP_SANITIZED.search(text)
            if kind in ("Cross-Site Scripting (XSS)", "Command Injection") and escaped:
                continue
            c.add(kind, severity, line, description)


# ----------------------------------------------------------- C# path traversal

_CS_FILE_API = re.compile(
    r"\b(File\.(Read\w*|Open\w*|Delete|Write\w*|Copy|Move)|PhysicalFile|Directory\.Delete)\s*\("
    r"[^;]*(Request\.|\bfileName\b|\bfilename\b|\bpath\b\s*[,)])"
)
_CS_SAFE = re.compile(r"Path\.GetFileName|GetFullPath")


def _csharp_paths(c: _Collector) -> None:
    for line, _text in c.each(_CS_FILE_API):
        context = "\n".join(c.lines[max(0, line - 6) : line])
        if not _CS_SAFE.search(context):
            c.add(
                "Path Traversal",
                Severity.high,
                line,
                "File API called with a user-supplied path; keep it inside the base folder",
            )


# ------------------------------------------------- missing input validation

_INPUT_READ = {
    "javascript": re.compile(r"\breq\.(body|query|params)\b"),
    "java": re.compile(r"\b(getParameter|getHeader)\s*\(|@RequestParam\b|@RequestBody\b"),
    "csharp": re.compile(r"\bRequest\.(Form|Query)\["),
    "php": re.compile(_PHP_INPUT),
}
_VALIDATION = {
    "javascript": re.compile(
        r"\b(joi|yup|zod|ajv|validator|express-validator|celebrate)\b|"
        r"\b(validate|isValid|safeParse|parseInt|Number\(|typeof)\b"
    ),
    "java": re.compile(
        r"@Valid\b|@Validated\b|@NotNull|@NotBlank|@Size|@Pattern|Validator\b|"
        r"\.matches\(|Integer\.parseInt|isBlank\(\)|isEmpty\(\)"
    ),
    "csharp": re.compile(
        r"ModelState\.IsValid|\[Required\]|\[StringLength|\[Range|TryParse|"
        r"FluentValidation|Validator\."
    ),
    "php": re.compile(
        r"filter_input|filter_var|preg_match|is_numeric|ctype_|intval|\(int\)|"
        r"empty\(|strlen\(|in_array\(|validate"
    ),
}


def _validation(c: _Collector, language: str, source: str) -> None:
    reader = _INPUT_READ.get(language)
    if reader is None or _VALIDATION[language].search(source):
        return
    for line, _ in c.each(reader):
        c.add(
            "Missing Input Validation",
            Severity.medium,
            line,
            "Request input is used without validation (type, length, format or range)",
        )
        return  # once per file is enough to make the point


# --------------------------------------------------------------- N+1 queries

_LOOP = re.compile(r"^\s*(for|foreach|while)\b|\.(forEach|map)\s*\(")
_QUERY = re.compile(
    r"\.(executeQuery|executeUpdate|query|execute|findById|findOne|findByPk|"
    r"find|get|first|load|ExecuteReader|ExecuteScalar|FirstOrDefault|Find)\s*\(|"
    r"\b(mysqli_query|pg_query)\s*\(|->\s*(query|find|first)\s*\("
)
_QUERY_HINT = re.compile(
    r"sql|query|repo|repository|db|conn|cursor|stmt|statement|"
    r"context|dbset|model|orm|session|knex|prisma|mongoose|\$pdo|\$conn",
    re.I,
)


def n_plus_one(path: str, source: str) -> list[dict]:
    """Queries issued once per loop iteration (brace languages; Python uses the AST)."""
    language = _LANG_BY_EXT.get(_ext(path))
    if language in (None, "python"):
        return []
    found: list[dict] = []
    lines = source.splitlines()
    loop_depths: list[int] = []
    depth = 0
    pending_loop = False
    for number, raw in enumerate(lines, start=1):
        line = _strip_comment(raw)
        if _LOOP.search(line):
            pending_loop = True
        if loop_depths and _QUERY.search(line) and _QUERY_HINT.search(line):
            found.append(
                {
                    "type": "n_plus_one_query",
                    "file": path,
                    "line": number,
                    "symbol": "",
                    "message": "Database query inside a loop (N+1): fetch the rows in one query "
                    "(JOIN / IN / eager loading) instead",
                }
            )
        for char in line:
            if char == "{":
                depth += 1
                if pending_loop:
                    loop_depths.append(depth)
                    pending_loop = False
            elif char == "}":
                if loop_depths and loop_depths[-1] == depth:
                    loop_depths.pop()
                depth = max(0, depth - 1)
    return found


_PY_QUERY_METHODS = {
    "execute",
    "executemany",
    "query",
    "get",
    "filter",
    "filter_by",
    "first",
    "one",
    "all",
    "scalar",
    "scalars",
    "find",
    "find_one",
    "fetchone",
    "fetchall",
}
_PY_QUERY_RECEIVERS = re.compile(r"cursor|cur|conn|db|session|objects|query|collection|repo", re.I)


def _python_n_plus_one(path: str, source: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return []
    found: dict[int, dict] = {}
    for loop in ast.walk(tree):
        if not isinstance(loop, ast.For | ast.AsyncFor | ast.While):
            continue
        for stmt in loop.body:
            for node in ast.walk(stmt):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in _PY_QUERY_METHODS:
                    continue
                receiver = ast.unparse(node.func.value)
                if _PY_QUERY_RECEIVERS.search(receiver) and node.lineno not in found:
                    found[node.lineno] = {
                        "type": "n_plus_one_query",
                        "file": path,
                        "line": node.lineno,
                        "symbol": receiver[:60],
                        "message": "Database query inside a loop (N+1): fetch the rows in one "
                        "query (JOIN / IN / eager loading) instead",
                    }
    return [found[line] for line in sorted(found)]


def find_n_plus_one(path: str, source: str) -> list[dict]:
    if _ext(path) == ".py":
        return _python_n_plus_one(path, source)
    return n_plus_one(path, source)


def scan_web(path: str, source: str) -> list[Vulnerability]:
    language = _LANG_BY_EXT.get(_ext(path))
    if language is None:
        return []
    collector = _Collector(path, source.splitlines())
    _csrf(collector, language, source)
    if language == "php":
        _php(collector)
    if language == "csharp":
        _csharp_paths(collector)
    _validation(collector, language, source)
    return collector.findings
