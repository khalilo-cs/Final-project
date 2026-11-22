import textwrap

from app.analyzers.javascript_analyzer import JavaScriptAnalyzer
from app.security.js_rules import scan_javascript
from tests.test_api import make_zip, upload


def analyze(code: str, path="app.js"):
    return JavaScriptAnalyzer().analyze(path, textwrap.dedent(code))


def kinds(code: str, path="server.js"):
    return [(f.type, f.line) for f in scan_javascript(path, textwrap.dedent(code))]


def test_complexity_matches_python_and_java():
    # Same shape as the Python and Java tests -> the same scores.
    result = analyze(
        """
        function branchy(items, flag) {
          let total = 0;
          for (const item of items) {
            if (item > 0 && flag) {
              total += item;
            } else if (item < -10) {
              total -= 1;
            } else {
              while (total > 100) {
                total = total / 2;
              }
            }
          }
          return total;
        }
        """
    )
    (function,) = result.functions
    assert function.cyclomatic_complexity == 6
    assert function.cognitive_complexity == 9
    assert function.max_nesting == 3


def test_structure_js_jsx_and_ts():
    jsx = analyze(
        """
        import React, { useState } from "react";
        const axios = require("axios");

        export default function Books({ items }) {
          const [query, setQuery] = useState("");
          const visible = items.filter((b) => b.title.includes(query));
          return <ul>{visible.map((b) => <li key={b.id}>{b.title}</li>)}</ul>;
        }
        """,
        "Books.jsx",
    )
    assert jsx.parse_error is None and jsx.imports == ["react", "axios"]
    assert [f.name for f in jsx.functions] == ["Books"]

    ts = analyze(
        """
        // repository
        export class BookRepo extends Base {
          constructor(private db: Db) { super(); }
          async find(id: number, limit?: number): Promise<Book[]> {
            return this.db.query("SELECT * FROM books WHERE id = ?", [id]);
          }
        }
        """,
        "repo.ts",
    )
    assert ts.language == "typescript" and ts.parse_error is None
    (repo,) = ts.classes
    assert repo.bases == ["Base"] and repo.methods == ["constructor", "find"]
    find = next(f for f in ts.functions if f.name == "find")
    assert find.parameters == 2 and find.is_async and ts.comment_lines == 1


def test_express_vulnerabilities():
    found = kinds(
        """
        const { exec } = require("child_process");
        app.get("/user/:id", (req, res) => {
          db.query(`SELECT * FROM users WHERE id = ${req.params.id}`);
          db.query("SELECT * FROM users WHERE id = " + req.params.id);
          const sql = `DELETE FROM t WHERE n = '${req.body.n}'`;
          pool.query(sql);
          db.query("SELECT * FROM users WHERE id = ?", [req.params.id]);
          exec(`ping ${req.query.host}`);
          exec("ls -la");
          res.sendFile(__dirname + "/uploads/" + req.params.name);
          eval(req.body.code);
          crypto.createHash("md5").update(pw);
        });
        """
    )
    assert found == [
        ("SQL Injection", 4),
        ("SQL Injection", 5),
        ("SQL Injection", 7),
        ("Command Injection", 9),
        ("Path Traversal", 11),
        ("Code Injection", 12),
        ("Weak Hash Algorithm", 13),
    ]


def test_browser_xss():
    found = kinds(
        """
        el.innerHTML = location.hash;
        el.innerHTML = "<b>static</b>";
        el.textContent = userInput;
        document.write(params.get("q"));
        const C = () => <div dangerouslySetInnerHTML={{ __html: html }} />;
        """,
        "page.jsx",
    )
    assert [k for k, _ in found] == [
        "Cross-Site Scripting (XSS)",
        "Cross-Site Scripting (XSS)",
        "Cross-Site Scripting (XSS)",
    ]
    assert [line for _, line in found] == [2, 5, 6]


def test_javascript_project_through_the_api():
    archive = make_zip(
        {
            "package.json": '{"dependencies": {"express": "^4", "mysql2": "^3"}}',
            "server.js": 'const express = require("express");\n'
            'app.get("/", (req, res) => db.query(`SELECT * FROM t WHERE id=${req.query.id}`));\n',
            "node_modules/x/index.js": "eval(a)",
        }
    )
    body = upload(archive).json()
    assert body["code"]["languages"] == {"javascript": 1}
    assert [v["type"] for v in body["security"]["vulnerabilities"]] == [
        "SQL Injection",
        "Missing Input Validation",
    ]
    assert {t["name"] for t in body["stack"]["technologies"]} == {"Express", "MySQL"}
