"""C# and C/C++ findings get explained suggestions with a safe example (no automatic patch)."""

from collections.abc import Callable

from app.fixes.models import Fix
from app.security.cpp_rules import scan_cpp
from app.security.csharp_rules import scan_csharp
from app.security.models import Vulnerability

_CSHARP = {
    "SQL Injection": (
        "Use SqlParameter",
        "Text typed into a TextBox and concatenated into SQL can rewrite the query "
        "(e.g. ' OR '1'='1 logs in without a password).",
        'var cmd = new SqlCommand("SELECT * FROM users WHERE name = @name", con);\n'
        'cmd.Parameters.AddWithValue("@name", txtUser.Text);',
    ),
    "Command Injection": (
        "Run the program directly with fixed arguments",
        "Passing input through cmd.exe lets characters like & run extra commands.",
        'var info = new ProcessStartInfo("ping") { UseShellExecute = false };\n'
        "info.ArgumentList.Add(host);  // validated first\nProcess.Start(info);",
    ),
    "Insecure Deserialization": (
        "Use System.Text.Json",
        "BinaryFormatter can execute code chosen by whoever wrote the data.",
        "var order = JsonSerializer.Deserialize<Order>(json);",
    ),
    "Weak Hash Algorithm": (
        "Hash passwords with PBKDF2",
        "MD5/SHA-1 password hashes are cracked in seconds.",
        "byte[] hash = Rfc2898DeriveBytes.Pbkdf2(password, salt, 100_000,\n"
        "    HashAlgorithmName.SHA256, 32);",
    ),
    "Cross-Site Scripting (XSS)": (
        "Encode output",
        "Input written as HTML lets an attacker run JavaScript in other users' browsers.",
        "Response.Write(HttpUtility.HtmlEncode(name));",
    ),
}
_CPP = {
    "Buffer Overflow": (
        "Use a bounded read/copy or std::string",
        "Writing past the end of a fixed array corrupts memory and can crash or be exploited.",
        "char buf[64];\nfgets(buf, sizeof buf, stdin);\n// or\nstd::string name;\n"
        "std::getline(std::cin, name);",
    ),
    "Format String": (
        "Never use input as the format",
        "%n and %x in the input read or write memory.",
        'printf("%s", message);',
    ),
    "Command Injection": (
        "Avoid system() with input",
        "The shell interprets ; and && inside the input.",
        'execlp("ping", "ping", "-c", "1", host, (char*)nullptr);  // host validated first',
    ),
    "SQL Injection": (
        "Use a prepared statement",
        "Concatenated input can rewrite the query.",
        'sqlite3_prepare_v2(db, "SELECT * FROM users WHERE name = ?", -1, &stmt, nullptr);\n'
        "sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_TRANSIENT);",
    ),
    "Weak Hash Algorithm": (
        "Use a password hashing function",
        "MD5/SHA-1 hashes are cracked in seconds.",
        "PKCS5_PBKDF2_HMAC(pw, len, salt, saltlen, 100000, EVP_sha256(), 32, out);",
    ),
}


def _propose(
    scan: Callable[[str, str], list[Vulnerability]], table: dict
) -> Callable[[str, str], list[Fix]]:
    def propose(path: str, source: str) -> list[Fix]:
        fixes = []
        for finding in scan(path, source):
            if suggestion := table.get(finding.type):
                title, explanation, example = suggestion
                fixes.append(
                    Fix(
                        path,
                        finding.line,
                        finding.type,
                        title,
                        explanation,
                        "suggestion",
                        example=example,
                    ).finalize(source)
                )
        return fixes

    return propose


propose_csharp = _propose(scan_csharp, _CSHARP)
propose_cpp = _propose(scan_cpp, _CPP)
