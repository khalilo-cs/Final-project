import textwrap

from app.security.python_rules import scan_python
from app.security.web_rules import find_n_plus_one, scan_web


def kinds(path: str, code: str) -> list[str]:
    code = textwrap.dedent(code)
    found = scan_web(path, code)
    if path.endswith(".py"):
        found += scan_python(path, code)
    return sorted(f.type for f in found)


# ----------------------------------------------------------------- CSRF


def test_django_csrf_exempt_and_missing_middleware():
    assert kinds(
        "views.py",
        """
        from django.views.decorators.csrf import csrf_exempt
        @csrf_exempt
        def pay(request):
            return None
    """,
    ) == ["CSRF"]
    assert kinds(
        "settings.py",
        """
        MIDDLEWARE = [
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
        ]
    """,
    ) == ["CSRF"]
    assert (
        kinds(
            "settings.py",
            """
        MIDDLEWARE = [
            "django.middleware.csrf.CsrfViewMiddleware",
        ]
    """,
        )
        == []
    )


def test_flask_form_post_without_csrf_protection():
    code = """
        from flask import request
        @app.route("/transfer", methods=["POST"])
        def transfer():
            amount = int(request.form["amount"])
            return str(amount)
    """
    assert kinds("app.py", code) == ["CSRF"]
    protected = "from flask_wtf.csrf import CSRFProtect\n" + textwrap.dedent(code)
    assert kinds("app.py", protected) == []


def test_spring_csrf_disabled():
    assert kinds(
        "SecurityConfig.java",
        """
        http.csrf().disable().authorizeRequests();
    """,
    ) == ["CSRF"]
    assert kinds(
        "SecurityConfig.java",
        """
        http.csrf(csrf -> csrf.disable());
    """,
    ) == ["CSRF"]


def test_aspnet_post_without_antiforgery():
    code = """
        public class AccountController : Controller {
            [HttpPost]
            public IActionResult Delete(int id, string reason) { return Ok(); }
        }
    """
    assert "CSRF" in kinds("AccountController.cs", code)
    assert "CSRF" not in kinds(
        "AccountController.cs", code.replace("[HttpPost]", "[HttpPost]\n[ValidateAntiForgeryToken]")
    )
    api = code.replace("public class", "[ApiController]\npublic class")
    assert "CSRF" not in kinds("AccountController.cs", api)


def test_express_session_app_without_csrf():
    code = """
        const session = require('express-session');
        app.use(session({ secret: process.env.S }));
        app.post('/transfer', (req, res) => { if (typeof req.body.to !== 'string') return; res.send('ok'); });
    """
    assert kinds("server.js", code) == ["CSRF"]
    assert kinds("server.js", "const csrf = require('csurf');\n" + textwrap.dedent(code)) == []


# --------------------------------------------------------- Path traversal


def test_python_path_traversal_from_request():
    assert "Path Traversal" in kinds(
        "app.py",
        """
        from flask import request, send_file
        def download():
            name = request.args.get("file")
            if not name:
                return "missing"
            return send_file("uploads/" + name)
    """,
    )
    assert "Path Traversal" not in kinds(
        "app.py",
        """
        from flask import request, send_file
        from werkzeug.utils import secure_filename
        def download():
            name = secure_filename(request.args.get("file"))
            if not name:
                return "missing"
            return send_file("uploads/" + name)
    """,
    )


def test_php_injections():
    found = kinds(
        "index.php",
        """
        <?php
        $id = $_GET['id'];
        $r = mysqli_query($conn, "SELECT * FROM users WHERE id = " . $_GET['id']);
        include($_GET['page'] . ".php");
        echo $_POST['name'];
        echo htmlspecialchars($_POST['name']);
        system("ping " . $_GET['host']);
    """,
    )
    assert found.count("SQL Injection") == 1
    assert found.count("Path Traversal") == 1
    assert found.count("Cross-Site Scripting (XSS)") == 1
    assert found.count("Command Injection") == 1
    assert "Missing Input Validation" in found


def test_csharp_file_api_with_user_path():
    assert "Path Traversal" in kinds(
        "FilesController.cs",
        """
        [ApiController]
        public class FilesController {
            public IActionResult Get(string fileName) {
                if (!ModelState.IsValid) return BadRequest();
                return PhysicalFile("/data/" + fileName, "application/pdf");
            }
        }
    """,
    )


# --------------------------------------------------- Input validation


def test_python_missing_input_validation():
    assert kinds(
        "app.py",
        """
        from flask import request
        def register():
            db.session.add(User(name=request.json["name"]))
    """,
    ) == ["Missing Input Validation"]
    assert (
        kinds(
            "app.py",
            """
        from flask import request
        def register():
            name = request.json["name"]
            if len(name) > 50:
                return "too long", 400
            db.session.add(User(name=name))
    """,
        )
        == []
    )


def test_java_validation_annotations_count_as_validation():
    code = """
        @PostMapping("/users")
        public User create(@RequestBody UserDto dto) { return repo.save(dto.toUser()); }
    """
    assert kinds("UserController.java", code) == ["Missing Input Validation"]
    assert kinds("UserController.java", code.replace("@RequestBody", "@Valid @RequestBody")) == []


# ----------------------------------------------------------------- N+1


def test_n_plus_one_python_and_java():
    py = find_n_plus_one(
        "orders.py",
        textwrap.dedent("""
        def totals(cursor, users):
            for user in users:
                cursor.execute("SELECT * FROM orders WHERE user_id = %s", (user.id,))
            cursor.execute("SELECT 1")
    """),
    )
    assert [item["line"] for item in py] == [4]
    java = find_n_plus_one(
        "Report.java",
        textwrap.dedent("""
        for (User u : users) {
            List<Order> o = orderRepository.findById(u.getId());
        }
        orderRepository.findById(1);
    """),
    )
    assert [item["line"] for item in java] == [3]
