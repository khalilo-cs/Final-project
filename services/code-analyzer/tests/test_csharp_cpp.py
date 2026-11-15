import textwrap

from app.analyzers.cpp_analyzer import CppAnalyzer
from app.analyzers.csharp_analyzer import CSharpAnalyzer
from app.fixes.native_fixes import propose_cpp, propose_csharp
from app.security.cpp_rules import scan_cpp
from app.security.csharp_rules import scan_csharp
from tests.test_api import make_zip, upload


def cs_kinds(code: str):
    return [(f.type, f.line) for f in scan_csharp("Form1.cs", textwrap.dedent(code))]


def cpp_kinds(code: str):
    return [(f.type, f.line) for f in scan_cpp("main.cpp", textwrap.dedent(code))]


def test_complexity_matches_other_languages():
    # Same shape as the Python/Java/JS tests -> the same scores.
    cs = CSharpAnalyzer().analyze(
        "A.cs",
        """
        class A {
          int Branchy(int[] items, bool flag) {
            int total = 0;
            foreach (var item in items) {
              if (item > 0 && flag) { total += item; }
              else if (item < -10) { total -= 1; }
              else { while (total > 100) { total = total / 2; } }
            }
            return total;
          }
        }
        """,
    )
    cpp = CppAnalyzer().analyze(
        "a.cpp",
        """
        int branchy(std::vector<int> items, bool flag) {
          int total = 0;
          for (int item : items) {
            if (item > 0 && flag) { total += item; }
            else if (item < -10) { total -= 1; }
            else { while (total > 100) { total = total / 2; } }
          }
          return total;
        }
        """,
    )
    for result in (cs, cpp):
        (function,) = result.functions
        assert (function.cyclomatic_complexity, function.cognitive_complexity) == (6, 9)
        assert function.max_nesting == 3


def test_csharp_structure():
    result = CSharpAnalyzer().analyze(
        "Shop/LoginForm.cs",
        textwrap.dedent(
            """
            using System.Data.SqlClient;
            using System.Windows.Forms;
            namespace Shop {
              [Serializable]
              public partial class LoginForm : Form, IView {
                public LoginForm() { InitializeComponent(); }
                public async Task<int> Count(int x, string y = "") { return x > 0 ? 1 : 0; }
              }
              interface IView {}
              enum Role { Admin, Student }
            }
            """
        ),
    )
    assert result.parse_error is None
    assert result.imports == ["System.Data.SqlClient", "System.Windows.Forms"]
    login = result.classes[0]
    assert (login.name, login.bases, login.decorators) == (
        "LoginForm",
        ["Form", "IView"],
        ["Serializable"],
    )
    assert [c.name for c in result.classes] == ["LoginForm", "IView", "Role"]
    count = result.functions[1]
    assert (count.qualified_name, count.parameters, count.is_async) == ("LoginForm.Count", 2, True)
    assert count.cyclomatic_complexity == 2


def test_cpp_structure():
    result = CppAnalyzer().analyze(
        "src/account.cpp",
        textwrap.dedent(
            """
            #include <iostream>
            #include "account.h"
            namespace bank {
            class Account : public Base {
             public:
              int balance() const { return value; }
              void deposit(double amount);
            };
            }
            void bank::Account::deposit(double amount) { if (amount > 0) value += amount; }
            int main(void) { return 0; }
            """
        ),
    )
    assert result.language == "cpp"
    assert result.imports == ["iostream", "account.h"]
    (account,) = result.classes
    assert (account.bases, account.methods) == (["Base"], ["balance", "deposit"])
    names = [(f.name, f.qualified_name, f.parameters) for f in result.functions]
    assert names == [
        ("balance", "Account.balance", 0),
        ("deposit", "bank.Account.deposit", 1),
        ("main", "main", 0),
    ]
    assert CppAnalyzer().analyze("x.c", "int f(int a) { return a; }").language == "c"


def test_csharp_sql_injection_from_textboxes():
    findings = cs_kinds(
        """
        void Login() {
          string q = "select * from users where name='" + txtUser.Text + "'";
          SqlCommand cmd = new SqlCommand(q, con);
          var safe = new SqlCommand("select * from users where name=@n", con);
          string q2 = "DELETE FROM items WHERE id=";
          q2 += txtId.Text;
          cmd.CommandText = q2;
          cmd.CommandText = $"UPDATE t SET a={x}";
          cmd.CommandText = "SELECT 1";
          var da = new SqlDataAdapter("SELECT * FROM t WHERE c='" + cat + "'", con);
          db.Database.ExecuteSqlRaw($"DELETE FROM t WHERE id={id}");
          db.Database.ExecuteSqlRaw("DELETE FROM t WHERE id={0}", id);
        }
        """
    )
    assert findings == [
        ("SQL Injection", 4),
        ("SQL Injection", 8),
        ("SQL Injection", 9),
        ("SQL Injection", 11),
        ("SQL Injection", 12),
    ]


def test_csharp_other_rules():
    findings = cs_kinds(
        """
        [ValidateInput(false)]
        void Run() {
          var h = MD5.Create();
          var sha = new SHA256Managed();
          var bf = new BinaryFormatter();
          Process.Start("cmd.exe", "/c " + txtCmd.Text);
          Process.Start("notepad.exe");
          Response.Write(Request.QueryString["name"]);
          var s = new JsonSerializerSettings { TypeNameHandling = TypeNameHandling.All };
          ServicePointManager.ServerCertificateValidationCallback = (a, b, c, d) => true;
        }
        """
    )
    assert sorted(findings) == sorted(
        [
            ("Cross-Site Scripting (XSS)", 2),
            ("Weak Hash Algorithm", 4),
            ("Insecure Deserialization", 6),
            ("Command Injection", 7),
            ("Cross-Site Scripting (XSS)", 9),
            ("Insecure Deserialization", 10),
            ("Disabled TLS Verification", 11),
        ]
    )


def test_cpp_rules():
    findings = cpp_kinds(
        """
        int main(int argc, char** argv) {
          char buf[10];
          gets(buf);
          strcpy(buf, argv[1]);
          strcpy(buf, "ok");
          system(argv[1]);
          system("cls");
          scanf("%s", buf);
          scanf("%9s", buf);
          printf(buf);
          printf("%s", buf);
          std::string q = "SELECT * FROM users WHERE name='" + std::string(argv[1]) + "'";
          mysql_query(conn, q.c_str());
          mysql_query(conn, "SELECT 1");
          return 0;
        }
        """
    )
    assert findings == [
        ("Buffer Overflow", 4),
        ("Buffer Overflow", 5),
        ("Command Injection", 7),
        ("Buffer Overflow", 9),
        ("Format String", 11),
        ("SQL Injection", 14),
    ]


def test_suggestions_for_csharp_and_cpp():
    cs = propose_csharp(
        "F.cs",
        'class F { void A() { var c = new SqlCommand("SELECT * FROM t WHERE a=" + x, con); } }',
    )
    assert [(f.kind, f.title) for f in cs] == [("suggestion", "Use SqlParameter")]
    cpp = propose_cpp("m.c", "int main() { char b[4]; gets(b); }")
    assert "fgets" in cpp[0].example


def test_dotnet_project_through_the_api():
    archive = make_zip(
        {
            "Shop/Shop.csproj": '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<UseWindowsForms>true</UseWindowsForms></PropertyGroup></Project>",
            "Shop/Form1.cs": "using System.Data.SqlClient;\nclass Form1 { void Go() {\n"
            '  var cmd = new SqlCommand("SELECT * FROM t WHERE n=\'" + txtName.Text + "\'", con);\n'
            "} }\n",
            "Shop/App.config": '<add connectionString="Data Source=.;Initial Catalog=Shop;'
            'Integrated Security=True" />',
            "Shop/bin/Debug/Gen.cs": "class G { void X() { eval(a); } }",
            "native/main.cpp": "#include <sqlite3.h>\nint main() { char b[8]; gets(b); }\n",
        }
    )
    body = upload(archive).json()
    assert body["code"]["languages"] == {"csharp": 1, "cpp": 1}
    found = sorted((v["type"], v["file"]) for v in body["security"]["vulnerabilities"])
    assert found == [("Buffer Overflow", "native/main.cpp"), ("SQL Injection", "Shop/Form1.cs")]
    technologies = {t["name"] for t in body["stack"]["technologies"]}
    assert {"SQL Server", "Windows Forms", "SQLite"} <= technologies
