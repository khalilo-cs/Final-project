import textwrap

from app.analyzers.java_analyzer import JavaAnalyzer
from app.quality.code_smells import detect_smells
from app.security.java_rules import scan_java
from app.security.models import Severity


def analyze(code: str):
    return JavaAnalyzer().analyze("Sample.java", textwrap.dedent(code))


def scan(code: str):
    return scan_java("App.java", textwrap.dedent(code))


def kinds(code: str):
    return [finding.type for finding in scan(code)]


# ---- structure -----------------------------------------------------------------------


def test_extracts_structure():
    result = analyze(
        """
        package edu.sanaa.library;

        import java.util.List;
        import static java.lang.Math.max;

        /**
         * Book repository.
         */
        @Repository
        public class BookRepository extends BaseRepository implements Repo, Closeable {
            private final List<String> books;  // field

            public BookRepository(List<String> books) { this.books = books; }

            @Override
            public <T> void add(String title, int year, T... tags) { }

            static class Cache { void clear() { } }
        }

        interface Repo extends AutoCloseable { void close(); }

        enum Status { ACTIVE, ARCHIVED; String label() { return name(); } }

        record Book(String title) { }
        """
    )
    assert result.parse_error is None
    assert result.imports == ["java.util.List", "java.lang.Math.max"]
    classes = {c.name: c for c in result.classes}
    assert list(classes) == ["BookRepository", "BookRepository.Cache", "Repo", "Status", "Book"]
    repo = classes["BookRepository"]
    assert repo.bases == ["BaseRepository", "Repo", "Closeable"]
    assert repo.methods == ["BookRepository", "add"]
    assert repo.decorators == ["Repository"]
    assert classes["Repo"].bases == ["AutoCloseable"]
    assert classes["Status"].methods == ["label"]

    functions = {f.qualified_name: f for f in result.functions}
    assert set(functions) == {
        "BookRepository.BookRepository",
        "BookRepository.add",
        "BookRepository.Cache.clear",
        "Repo.close",
        "Status.label",
    }
    assert functions["BookRepository.add"].parameters == 3
    assert functions["BookRepository.add"].decorators == ["Override"]
    assert functions["Repo.close"].cyclomatic_complexity == 1  # no body

    assert result.comment_lines == 3  # the javadoc; the trailing `// field` shares a code line
    assert result.total_lines == result.code_lines + result.blank_lines + result.comment_lines


def test_complexity_matches_python_rules():
    # Same shape as the Python test in test_python_analyzer.py -> same scores.
    result = analyze(
        """
        class C {
            int simple() { return 1; }

            int branchy(int[] items, boolean flag) {
                int total = 0;
                for (int item : items) {
                    if (item > 0 && flag) {
                        total += item;
                    } else if (item < -10) {
                        total -= 1;
                    } else {
                        while (total > 100) {
                            total /= 2;
                        }
                    }
                }
                return total;
            }
        }
        """
    )
    simple, branchy = result.functions
    assert (simple.cyclomatic_complexity, simple.cognitive_complexity) == (1, 0)
    assert branchy.cyclomatic_complexity == 6
    assert branchy.cognitive_complexity == 9
    assert branchy.max_nesting == 3


def test_complexity_switch_ternary_catch_lambda():
    result = analyze(
        """
        class C {
            int m(int x) {
                switch (x) {          // cyc +2 (two cases), cog +1
                    case 1: return 1;
                    case 2: return 2;
                    default: break;
                }
                int y = x > 0 ? 1 : 0;           // cyc +1, cog +1
                try { y++; }
                catch (Exception e) { y--; }     // cyc +1, cog +1
                Runnable r = () -> { if (y > 0) { } };  // cyc +1, cog +2 (nested in lambda)
                return a || b || c ? y : 0;      // cyc +3, cog +1 (ternary) +1 (one || run)
            }
        }
        """
    )
    (method,) = result.functions
    assert method.cyclomatic_complexity == 1 + 2 + 1 + 1 + 1 + 3
    assert method.cognitive_complexity == 1 + 1 + 1 + 2 + 2


def test_syntax_error_reported_but_structure_kept():
    result = analyze("class A {\n  void ok() { }\n  void broken( { }\n}\n")
    assert result.parse_error.startswith("SyntaxError")
    assert "A" in [c.name for c in result.classes]


def test_deep_expression_does_not_overflow():
    expression = " + ".join(f'"s{i}"' for i in range(5000))
    result = analyze(f"class D {{ String m() {{ return {expression}; }} }}")
    assert result.functions[0].cyclomatic_complexity == 1
    assert scan(f"class D {{ void m(Statement s) {{ s.execute({expression}); }} }}") == []


def test_java_smells():
    methods = "\n".join(f"    void m{i}() {{ }}" for i in range(21))
    code = f"class Everything {{\n{methods}\n  void many(int a, int b, int c, int d, int e, int f) {{ }}\n}}"
    smells = {(s.type, s.symbol) for s in detect_smells(JavaAnalyzer().analyze("E.java", code))}
    assert smells == {("god_class", "Everything"), ("too_many_parameters", "Everything.many")}


# ---- security ------------------------------------------------------------------------


def test_sql_injection_variants():
    findings = scan(
        """
        class Dao {
            void a(Statement st, String name) throws Exception {
                st.executeQuery("SELECT * FROM users WHERE name = '" + name + "'");
            }
            void b(Connection c, String id) throws Exception {
                String sql = "DELETE FROM users WHERE id = " + id;
                c.createStatement().executeUpdate(sql);
            }
            void c(Connection c, String id) throws Exception {
                c.prepareStatement(String.format("SELECT * FROM t WHERE id = %s", id));
            }
            void d(EntityManager em, String n) {
                String q = "SELECT u FROM User u";
                q += " WHERE u.name = '" + n + "'";
                em.createQuery(q);
            }
            void e(JdbcTemplate jdbc, String n) {
                jdbc.queryForList("SELECT * FROM t WHERE n = '%s'".formatted(n));
            }
        }
        """
    )
    assert [(f.type, f.line) for f in findings] == [
        ("SQL Injection", 4),
        ("SQL Injection", 8),
        ("SQL Injection", 11),
        ("SQL Injection", 16),
        ("SQL Injection", 19),
    ]
    assert all(f.severity is Severity.critical for f in findings)


def test_safe_sql_is_clean():
    assert not scan(
        """
        class Dao {
            void ok(Connection c, String name) throws Exception {
                PreparedStatement ps = c.prepareStatement("SELECT * FROM users WHERE name = ?");
                ps.setString(1, name);
                ps.executeQuery();
                String sql = "SELECT * FROM users " + "WHERE active = 1";
                c.createStatement().executeQuery(sql);
                final int LIMIT = 10;
                list.add("item " + name);
            }
            void other(Statement st) throws Exception {
                st.executeQuery(sql);   // `sql` was tainted only inside another method
            }
        }
        """
    )


def test_servlet_xss_and_path_traversal():
    findings = scan(
        """
        class Servlet extends HttpServlet {
            protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
                String name = req.getParameter("name");
                PrintWriter out = resp.getWriter();
                out.println("<h1>Hello " + name + "</h1>");
                resp.getWriter().write(req.getParameter("q"));
                out.println("static text");
                File f = new File("/uploads/" + req.getParameter("file"));
                Path p = Paths.get(name);
            }
        }
        """
    )
    assert [(f.type, f.line) for f in findings] == [
        ("Cross-Site Scripting (XSS)", 6),
        ("Cross-Site Scripting (XSS)", 7),
        ("Path Traversal", 9),
        ("Path Traversal", 10),
    ]


def test_command_deserialization_crypto():
    assert kinds(
        """
        class X {
            void m(String cmd, InputStream in) throws Exception {
                Runtime.getRuntime().exec(cmd);
                Runtime.getRuntime().exec("ls -la");
                new ProcessBuilder("bash", "-c", cmd).start();
                new ProcessBuilder("ls", "-la").start();
                Object o = new ObjectInputStream(in).readObject();
                MessageDigest.getInstance("MD5");
                MessageDigest.getInstance("SHA-256");
                Cipher.getInstance("DES/CBC/PKCS5Padding");
                Cipher.getInstance("AES/GCM/NoPadding");
            }
        }
        """
    ) == [
        "Command Injection",
        "Command Injection",
        "Insecure Deserialization",
        "Weak Hash Algorithm",
        "Weak Cryptography",
    ]
