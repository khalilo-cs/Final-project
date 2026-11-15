"""Work out how to build and start a student project (plan, week 20)."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunPlan:
    stack: str
    image: str
    workdir: str  # project folder inside the container (relative to /app)
    build: list[str] = field(default_factory=list)  # shell commands, network allowed
    start: str = ""
    port: int = 8000
    notes: list[str] = field(default_factory=list)


class UnsupportedProject(Exception):
    pass


def _find(root: Path, name: str) -> Path | None:
    """The shallowest file with this name (projects are often zipped inside a folder)."""
    matches = sorted(root.rglob(name), key=lambda p: (len(p.parts), str(p)))
    matches = [m for m in matches if "node_modules" not in m.parts and ".git" not in m.parts]
    return matches[0] if matches else None


def _rel(root: Path, path: Path) -> str:
    folder = path.parent.relative_to(root).as_posix()
    return "" if folder == "." else folder


def _python(root: Path) -> RunPlan | None:
    requirements = _find(root, "requirements.txt")
    manage = _find(root, "manage.py")
    entry = next(
        (
            p
            for name in ("app.py", "main.py", "run.py", "server.py", "wsgi.py")
            if (p := _find(root, name))
        ),
        None,
    )
    anchor = manage or entry or requirements
    if anchor is None:
        return None
    folder = _rel(root, anchor)
    build = []
    if requirements:
        build.append(f"pip install --no-cache-dir -r {requirements.relative_to(root).as_posix()}")
    if manage:
        build.append("pip install --no-cache-dir django || true")
        return RunPlan(
            "django",
            "python:3.12-slim",
            folder,
            build,
            "python manage.py migrate --noinput || true; "
            "python manage.py runserver 0.0.0.0:8000 --noreload",
            8000,
        )
    text = (requirements.read_text(errors="replace").lower() if requirements else "") + (
        entry.read_text(errors="replace") if entry else ""
    )
    module = entry.stem if entry else "app"
    if "fastapi" in text.lower():
        build.append("pip install --no-cache-dir uvicorn fastapi")
        variable = _app_variable(entry, "FastAPI") or "app"
        return RunPlan(
            "fastapi",
            "python:3.12-slim",
            folder,
            build,
            f"uvicorn {module}:{variable} --host 0.0.0.0 --port 8000",
            8000,
        )
    if "flask" in text.lower():
        build.append("pip install --no-cache-dir flask")
        variable = _app_variable(entry, "Flask") or "app"
        return RunPlan(
            "flask",
            "python:3.12-slim",
            folder,
            build,
            f"flask --app {module}:{variable} run --host 0.0.0.0 --port 8000",
            8000,
        )
    if entry:
        return RunPlan(
            "python",
            "python:3.12-slim",
            folder,
            build,
            f"python {entry.name}",
            8000,
            ["No web framework found: the program is run, not load-tested"],
        )
    return None


def _app_variable(entry: Path | None, cls: str) -> str | None:
    if entry is None:
        return None
    match = re.search(rf"^(\w+)\s*=\s*{cls}\(", entry.read_text(errors="replace"), re.M)
    return match[1] if match else None


def _node(root: Path) -> RunPlan | None:
    package = _find(root, "package.json")
    if package is None:
        return None
    try:
        data = json.loads(package.read_text(errors="replace"))
    except json.JSONDecodeError as exc:
        raise UnsupportedProject("package.json is not valid JSON") from exc
    scripts = data.get("scripts") or {}
    dependencies = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    folder = _rel(root, package)
    if "start" in scripts:
        start = "PORT=8000 npm start"
    elif data.get("main"):
        start = f"PORT=8000 node {data['main']}"
    elif "vite" in dependencies or "react-scripts" in dependencies:
        return RunPlan(
            "node-frontend",
            "node:22-slim",
            folder,
            ["npm install", "npm run build"],
            "npx --yes serve -s dist -l 8000 || npx --yes serve -s build -l 8000",
            8000,
        )
    else:
        raise UnsupportedProject("package.json has no start script")
    return RunPlan(
        "node", "node:22-slim", folder, ["npm install --omit=dev || npm install"], start, 8000
    )


def _php(root: Path) -> RunPlan | None:
    index = _find(root, "index.php")
    if index is None:
        return None
    public = _find(root, "artisan")  # Laravel serves from public/
    if public:
        return RunPlan(
            "laravel",
            "php:8.3-cli",
            _rel(root, public),
            [],
            "php -S 0.0.0.0:8000 -t public",
            8000,
            ["Laravel without composer install may fail to start"],
        )
    return RunPlan("php", "php:8.3-cli", _rel(root, index), [], "php -S 0.0.0.0:8000", 8000)


def _java(root: Path) -> RunPlan | None:
    pom = _find(root, "pom.xml")
    if pom is None:
        return None
    return RunPlan(
        "java-maven",
        "maven:3.9-eclipse-temurin-21",
        _rel(root, pom),
        ["mvn -q -DskipTests package"],
        "java -jar $(ls target/*.jar | grep -v original | head -1) --server.port=8000",
        8000,
    )


def _static(root: Path) -> RunPlan | None:
    index = _find(root, "index.html")
    if index is None:
        return None
    return RunPlan(
        "static", "python:3.12-slim", _rel(root, index), [], "python -m http.server 8000", 8000
    )


def detect(root: Path) -> RunPlan:
    for detector in (_node, _python, _java, _php, _static):
        plan = detector(root)
        if plan is not None:
            return plan
    raise UnsupportedProject("Could not tell how to start this project")
