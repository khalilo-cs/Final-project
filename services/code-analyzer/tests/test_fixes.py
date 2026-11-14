import base64
import io
import json
import textwrap
import zipfile

from app.fixes.models import apply_edits
from app.fixes.python_fixes import propose_python
from tests.test_api import auth, client, make_zip

VULNERABLE = textwrap.dedent(
    '''\
    """Library app."""
    import sqlite3
    import yaml
    import requests

    DB_PASSWORD = "Sup3rS3cret!"


    def find(conn, name, user):
        conn.execute(f"SELECT * FROM users WHERE name = '{name}' AND id = {user.id}")
        conn.execute("DELETE FROM t WHERE n = '" + name + "'")


    def load(path):
        return yaml.load(open(path))


    def fetch():
        return requests.get("https://x", verify=False)
    '''
)


def by_type(fixes):
    return {fix.type: fix for fix in fixes}


def test_python_patches():
    fixes = propose_python("app.py", VULNERABLE)
    patched = apply_edits(VULNERABLE, [e for f in fixes if f.kind == "patch" for e in f.edits])
    patched = apply_edits(patched, [], "import os")
    assert (
        "conn.execute('SELECT * FROM users WHERE name = ? AND id = ?', (name, user.id,))" in patched
    )
    assert "conn.execute('DELETE FROM t WHERE n = ?', (name,))" in patched
    assert "yaml.safe_load(open(path))" in patched
    assert "verify=True" in patched
    assert 'DB_PASSWORD = os.environ["DB_PASSWORD"]' in patched
    assert patched.splitlines()[1] == "import os"  # after the docstring
    compile(patched, "app.py", "exec")


def test_placeholder_follows_the_driver():
    code = "import pymysql\ndef f(c, n):\n    c.execute(f'SELECT * FROM t WHERE n = {n}')\n"
    (fix,) = propose_python("a.py", code)
    assert "%s" in apply_edits(code, fix.edits)


def test_unsafe_rewrites_become_suggestions():
    code = textwrap.dedent(
        """\
        import hashlib
        def f(c, n):
            c.execute("SELECT * FROM t WHERE n = '{}'".format(n.strip()))
            return hashlib.md5(n.encode())
        """
    )
    fixes = propose_python("a.py", code)
    assert [(f.type, f.kind) for f in fixes] == [
        ("SQL Injection", "suggestion"),
        ("Weak Hash Algorithm", "suggestion"),
    ]


def upload_fixes(path, data, **form):
    return client.post(
        f"/api/v1/fixes/{path}",
        files={"file": ("code.zip", data, "application/zip")},
        data=form,
        headers=auth(),
    )


def test_propose_and_apply_api():
    java = 'class D { void f(Statement s, String n) { s.executeQuery("SELECT * FROM t WHERE n=\'" + n + "\'"); } }'
    archive = make_zip({"src/app.py": VULNERABLE, "src/D.java": java, "README.md": "# hi"})
    proposals = upload_fixes("propose", archive).json()
    patches = [p for p in proposals if p["kind"] == "patch"]
    assert len(patches) == 5
    assert all(p["diff"].startswith("--- a/src/app.py") for p in patches)
    java_fix = next(p for p in proposals if p["file"] == "src/D.java")
    assert java_fix["kind"] == "suggestion" and "PreparedStatement" in java_fix["example"]

    chosen = [p["id"] for p in patches if p["type"] == "SQL Injection"] + [java_fix["id"], "nope"]
    result = upload_fixes("apply", archive, fix_ids=json.dumps(chosen)).json()
    assert [a["type"] for a in result["applied"]] == ["SQL Injection", "SQL Injection"]
    assert {s["id"]: s["reason"] for s in result["skipped"]} == {
        java_fix["id"]: "advice only, change it by hand",
        "nope": "fix no longer applies",
    }
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["archive_base64"]))) as bundle:
        fixed = bundle.read("src/app.py").decode()
        assert bundle.read("README.md") == b"# hi" and bundle.read("src/D.java").decode() == java
    assert "?" in fixed and "yaml.load(" in fixed  # only the approved fixes were applied

    # Re-analysis confirms the SQL injections are gone.
    after = client.post(
        "/api/v1/analysis/code",
        files={"file": ("c.zip", base64.b64decode(result["archive_base64"]), "application/zip")},
        headers=auth(),
    ).json()["security"]
    python_types = [v["type"] for v in after["vulnerabilities"] if v["file"] == "src/app.py"]
    assert "SQL Injection" not in python_types

    assert upload_fixes("apply", archive, fix_ids="not json").status_code == 422
