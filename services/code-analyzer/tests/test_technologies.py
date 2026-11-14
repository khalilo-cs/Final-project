import io
import json
import zipfile

from app.analyzers.technologies import TechnologyDetector
from tests.test_api import upload


def names(result):
    return {t["name"] for t in result["technologies"]}


def test_manifests_imports_and_connection_strings():
    detector = TechnologyDetector()
    package = {"dependencies": {"react": "^18", "axios": "1"}, "devDependencies": {"vite": "5"}}
    detector.feed_manifest("web/package.json", json.dumps(package))
    detector.feed_manifest("requirements.txt", "Django==5.0\npsycopg2-binary>=2.9  # db\n# x\n")
    detector.feed_manifest("api/pom.xml", "<artifactId>spring-boot-starter-web</artifactId>")
    detector.feed_imports("app/Dao.java", ["java.sql.Connection", "javax.swing.JFrame"])
    detector.feed_imports("main.py", ["os", "flask"])
    detector.feed_text("Db.java", 'url = "jdbc:mysql://localhost/shop"')
    detector.feed_manifest("broken/package.json", "{not json")
    assert names(detector.result()) == {
        "React", "Django", "PostgreSQL", "Spring Boot", "JDBC", "Swing", "Flask", "MySQL",
    }  # fmt: skip


def test_languages_and_architecture():
    detector = TechnologyDetector()
    for path in [
        "app/Http/Controllers/UserController.php",
        "app/Models/User.php",
        "resources/views/home.blade.php",
        "public/app.js",
    ]:
        detector.feed_path(path)
    result = detector.result()
    assert result["languages"] == {"PHP": 3, "JavaScript": 1}
    assert result["architecture"] == ["MVC"]


def test_stack_in_api_response():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("requirements.txt", "flask\nPyMySQL\n")
        bundle.writestr("app.py", "import flask\n")
        bundle.writestr("static/site.css", "body {}")
        bundle.writestr("node_modules/react/package.json", '{"dependencies": {"vue": "3"}}')
    stack = upload(buffer.getvalue()).json()["stack"]
    assert stack["languages"] == {"Python": 1, "CSS": 1}
    assert names(stack) == {"Flask", "MySQL"}  # node_modules ignored
    flask = next(t for t in stack["technologies"] if t["name"] == "Flask")
    assert flask["evidence"] == ["app.py", "requirements.txt"]
