"""Java findings get explained suggestions: safe rewrites need the surrounding code."""

from app.fixes.models import Fix
from app.security.java_rules import scan_java

_SUGGESTIONS = {
    "SQL Injection": (
        "Use PreparedStatement",
        "Concatenating input into SQL lets an attacker change the query.",
        'PreparedStatement ps = connection.prepareStatement(\n    "SELECT * FROM users WHERE '
        'name = ?");\nps.setString(1, name);\nResultSet rs = ps.executeQuery();',
    ),
    "Cross-Site Scripting (XSS)": (
        "Encode output before writing it to the page",
        "Request input written as-is to HTML lets an attacker run JavaScript in other users' "
        "browsers.",
        "import org.owasp.encoder.Encode;\nout.println(Encode.forHtml(name));",
    ),
    "Path Traversal": (
        "Resolve the path and check it stays inside the upload folder",
        "Input like ../../etc/passwd escapes the intended folder.",
        'Path base = Paths.get("/uploads").toRealPath();\nPath file = base.resolve(name)'
        ".normalize();\nif (!file.startsWith(base)) throw new SecurityException();",
    ),
    "Command Injection": (
        "Pass arguments as a list, never through a shell",
        "A shell interprets characters like ; and && in the input.",
        'new ProcessBuilder("ping", "-c", "1", host).start();',
    ),
    "Weak Hash Algorithm": (
        "Use BCrypt for passwords",
        "MD5/SHA-1 hashes are cracked in seconds.",
        "String hash = BCrypt.hashpw(password, BCrypt.gensalt());",
    ),
}


def propose_java(path: str, source: str) -> list[Fix]:
    fixes = []
    for finding in scan_java(path, source):
        suggestion = _SUGGESTIONS.get(finding.type)
        if suggestion:
            title, explanation, example = suggestion
            fixes.append(
                Fix(path, finding.line, finding.type, title, explanation, "suggestion",
                    example=example).finalize(source)
            )  # fmt: skip
    return fixes
