import textwrap

from app.security.models import Severity
from app.security.python_rules import scan_python
from app.security.secrets_scanner import scan_secrets


def scan(code: str):
    return scan_python("app.py", textwrap.dedent(code))


def kinds(code: str):
    return [finding.type for finding in scan(code)]


def test_sql_injection_variants_detected():
    findings = scan(
        """
        def a(cur, name):
            cur.execute(f"SELECT * FROM users WHERE name = '{name}'")

        def b(cur, name):
            cur.execute("SELECT * FROM users WHERE name = '%s'" % name)

        def c(cur, name):
            cur.execute("SELECT * FROM users WHERE name = '" + name + "'")

        def d(cur, name):
            cur.execute("SELECT * FROM users WHERE name = '{}'".format(name))

        def e(cur, name):
            query = "SELECT * FROM users WHERE name = '" + name + "'"
            cur.execute(query)

        def f(session, name):
            session.execute(text(f"DELETE FROM users WHERE name = '{name}'"))
        """
    )
    assert [f.type for f in findings] == ["SQL Injection"] * 6
    assert all(f.severity is Severity.critical for f in findings)
    assert [f.line for f in findings] == [3, 6, 9, 12, 16, 19]


def test_parameterized_queries_are_clean():
    assert not scan(
        """
        def ok(cur, name, table_rows):
            cur.execute("SELECT * FROM users WHERE name = %s", (name,))
            cur.execute("SELECT * FROM users WHERE name = ?", [name])
            query = "SELECT * FROM users " "WHERE active = 1"
            cur.execute(query)
            cur.executemany("INSERT INTO t VALUES (?, ?)", table_rows)
        """
    )


def test_taint_does_not_leak_between_functions():
    assert not scan(
        """
        def build(name):
            query = "SELECT * FROM t WHERE n = '" + name + "'"
            return query

        def other(cur):
            query = "SELECT 1"
            cur.execute(query)
        """
    )


def test_command_and_code_injection():
    assert kinds(
        """
        import os, subprocess
        def run(user_input):
            os.system("ping " + user_input)
            subprocess.run(f"ls {user_input}", shell=True)
            eval(user_input)
            os.system("clear")
            subprocess.run(["ls", user_input])
            subprocess.run("ls -la", shell=True)
        """
    ) == ["Command Injection", "Command Injection", "Code Injection"]


def test_deserialization_and_misc_rules():
    findings = scan(
        """
        import pickle, yaml, hashlib, requests
        def load(blob, app):
            pickle.loads(blob)
            yaml.load(blob)
            yaml.load(blob, Loader=yaml.SafeLoader)
            yaml.safe_load(blob)
            requests.get("https://x", verify=False)
            hashlib.md5(blob)
            app.run(debug=True)
        """
    )
    assert [(f.type, f.severity) for f in findings] == [
        ("Insecure Deserialization", Severity.high),
        ("Insecure Deserialization", Severity.high),
        ("Disabled TLS Verification", Severity.medium),
        ("Weak Hash Algorithm", Severity.low),
        ("Debug Mode Enabled", Severity.medium),
    ]


def test_invalid_python_yields_no_findings():
    assert scan("def broken(:") == []


def test_secrets_detected_and_masked():
    source = textwrap.dedent(
        """
        DB_PASSWORD = "Sup3rS3cret!x"
        config = {"api_key": "9f8a7b6c5d4e3f2a1b0c"}
        AWS = "AKIAIOSFODNN7EXAMPLE"
        const token = 'eyJhbGciOiJIUzI1NiJ9abc';
        """
    )
    findings = scan_secrets("settings.py", source)
    assert [f.line for f in findings] == [2, 3, 4, 5]
    assert findings[2].severity is Severity.critical
    assert all("Sup3rS3cret" not in f.evidence for f in findings)
    assert findings[0].evidence == "DB_PASSWORD = Su******"


def test_secret_placeholders_ignored():
    source = textwrap.dedent(
        """
        password = os.environ["DB_PASSWORD"]
        PASSWORD = "changeme"
        api_key = "<your-key-here>"
        secret = "${SECRET}"
        password_label = "Enter your password"
        token_type = "bearer"
        password = ""
        """
    )
    assert scan_secrets("settings.py", source) == []
