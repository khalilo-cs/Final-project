"""Detect the languages, frameworks and databases a project really uses.

Evidence comes from file extensions, dependency manifests, imports and connection
strings. The report analyzer compares this against what the written report claims.
"""

import json
import re
import tomllib
from collections import Counter, defaultdict
from pathlib import PurePosixPath

EXTENSION_LANGUAGES = {
    ".py": "Python", ".java": "Java", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".c": "C", ".dart": "Dart",
    ".kt": "Kotlin", ".swift": "Swift", ".go": "Go", ".rb": "Ruby",
    ".html": "HTML", ".css": "CSS", ".sql": "SQL",
}  # fmt: skip

# Dependency name -> technology (npm, PyPI, Composer).
_PACKAGES = {
    "react": "React", "react-dom": "React", "react-native": "React Native", "vue": "Vue.js",
    "@angular/core": "Angular", "next": "Next.js", "express": "Express", "@nestjs/core": "NestJS",
    "jquery": "jQuery", "bootstrap": "Bootstrap", "tailwindcss": "Tailwind CSS",
    "typescript": "TypeScript", "socket.io": "Socket.IO", "jsonwebtoken": "JWT",
    "mongoose": "MongoDB", "mongodb": "MongoDB", "mysql": "MySQL", "mysql2": "MySQL",
    "pg": "PostgreSQL", "sqlite3": "SQLite", "better-sqlite3": "SQLite", "firebase": "Firebase",
    "sequelize": "Sequelize", "prisma": "Prisma", "@prisma/client": "Prisma",
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "sqlalchemy": "SQLAlchemy",
    "pymysql": "MySQL", "mysqlclient": "MySQL", "mysql-connector-python": "MySQL",
    "psycopg": "PostgreSQL", "psycopg2": "PostgreSQL", "psycopg2-binary": "PostgreSQL",
    "pymongo": "MongoDB", "tensorflow": "TensorFlow", "torch": "PyTorch",
    "scikit-learn": "scikit-learn", "opencv-python": "OpenCV", "pyjwt": "JWT",
    "redis": "Redis", "celery": "Celery", "laravel/framework": "Laravel",
}  # fmt: skip

# Import prefix -> technology.
_IMPORTS = {
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "sqlalchemy": "SQLAlchemy",
    "sqlite3": "SQLite", "pymysql": "MySQL", "MySQLdb": "MySQL", "mysql.connector": "MySQL",
    "psycopg": "PostgreSQL", "psycopg2": "PostgreSQL", "pymongo": "MongoDB",
    "tensorflow": "TensorFlow", "torch": "PyTorch", "sklearn": "scikit-learn", "cv2": "OpenCV",
    "tkinter": "Tkinter", "PyQt5": "PyQt", "PyQt6": "PyQt", "jwt": "JWT",
    "org.springframework": "Spring", "javax.servlet": "Servlets", "jakarta.servlet": "Servlets",
    "javax.swing": "Swing", "javafx": "JavaFX", "java.sql": "JDBC", "org.hibernate": "Hibernate",
    "javax.persistence": "JPA", "jakarta.persistence": "JPA", "android": "Android",
    "com.mysql": "MySQL", "org.postgresql": "PostgreSQL", "com.mongodb": "MongoDB",
    "io.jsonwebtoken": "JWT",
    # C# (using) and C/C++ (#include)
    "System.Data.SqlClient": "SQL Server", "Microsoft.Data.SqlClient": "SQL Server",
    "MySql.Data": "MySQL", "MySqlConnector": "MySQL", "Npgsql": "PostgreSQL",
    "System.Data.SQLite": "SQLite", "Microsoft.Data.Sqlite": "SQLite", "MongoDB.Driver": "MongoDB",
    "System.Data.OleDb": "MS Access", "System.Windows.Forms": "Windows Forms",
    "System.Windows.Controls": "WPF", "Microsoft.AspNetCore": "ASP.NET Core",
    "System.Web.Mvc": "ASP.NET MVC", "System.Web": "ASP.NET",
    "Microsoft.EntityFrameworkCore": "Entity Framework", "System.Data.Entity": "Entity Framework",
    "Dapper": "Dapper", "Newtonsoft.Json": "Json.NET",
    "mysql.h": "MySQL", "mysql/mysql.h": "MySQL", "sqlite3.h": "SQLite", "libpq-fe.h": "PostgreSQL",
    "opencv2": "OpenCV", "QApplication": "Qt", "QtWidgets": "Qt", "QtCore": "Qt", "QtSql": "Qt",
    "QWidget": "Qt", "QMainWindow": "Qt", "SFML": "SFML", "GL/glut.h": "OpenGL",
    "GL/gl.h": "OpenGL", "GLFW": "OpenGL", "boost": "Boost",
    # JavaScript / TypeScript (import "x" or require("x"))
    "react": "React", "vue": "Vue.js", "@angular/core": "Angular", "next": "Next.js",
    "express": "Express", "@nestjs/core": "NestJS", "mongoose": "MongoDB", "mongodb": "MongoDB",
    "mysql2": "MySQL", "mysql": "MySQL", "pg": "PostgreSQL", "sequelize": "Sequelize",
    "firebase": "Firebase", "socket.io": "Socket.IO", "jsonwebtoken": "JWT",
}  # fmt: skip

# Substrings in build files / sources.
_TEXT_SIGNALS = [
    ("jdbc:mysql", "MySQL"), ("jdbc:postgresql", "PostgreSQL"), ("jdbc:sqlite", "SQLite"),
    ("mongodb://", "MongoDB"), ("mongodb+srv://", "MongoDB"), ("mysql://", "MySQL"),
    ("postgresql://", "PostgreSQL"), ("spring-boot", "Spring Boot"),
    ("mysql-connector", "MySQL"), ("initial catalog=", "SQL Server"),
    ("microsoft.ace.oledb", "MS Access"), ("microsoft.jet.oledb", "MS Access"),
    ("microsoft.net.sdk.web", "ASP.NET Core"), ("<usewindowsforms>true", "Windows Forms"),
    ("<usewpf>true", "WPF"), ("find_package(qt", "Qt"),
    ("org.postgresql", "PostgreSQL"), ("hibernate", "Hibernate"),
]  # fmt: skip

_MANIFESTS = {"package.json", "requirements.txt", "pyproject.toml", "pipfile", "composer.json"}
_BUILD_FILES = {"pom.xml", "build.gradle", "build.gradle.kts", "pubspec.yaml"}
_BUILD_SUFFIXES = (".csproj", ".vcxproj", "cmakelists.txt", ".pro", "packages.config")
_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)")
MAX_MANIFEST_BYTES = 512_000


class TechnologyDetector:
    def __init__(self) -> None:
        self.extensions: Counter[str] = Counter()
        self.evidence: dict[str, set[str]] = defaultdict(set)
        self.directories: set[str] = set()

    def _found(self, technology: str, where: str) -> None:
        if len(self.evidence[technology]) < 5:
            self.evidence[technology].add(where)

    # -- inputs --------------------------------------------------------------------------

    def feed_path(self, relative: str) -> None:
        path = PurePosixPath(relative)
        if language := EXTENSION_LANGUAGES.get(path.suffix.lower()):
            self.extensions[language] += 1
        self.directories.update(part.lower() for part in path.parts[:-1])

    def wants_content(self, relative: str) -> bool:
        name = PurePosixPath(relative).name.lower()
        return name in _MANIFESTS or name in _BUILD_FILES or name.endswith(_BUILD_SUFFIXES)

    def feed_manifest(self, relative: str, content: str) -> None:
        name = PurePosixPath(relative).name.lower()
        for package in _manifest_packages(name, content):
            technology = _PACKAGES.get(package.lower())
            if technology:
                self._found(technology, relative)
        if name in _BUILD_FILES or name.endswith(_BUILD_SUFFIXES):
            self.feed_text(relative, content.lower())
            if name == "pubspec.yaml" and "flutter" in content:
                self._found("Flutter", relative)

    def feed_text(self, relative: str, content: str) -> None:
        for signal, technology in _TEXT_SIGNALS:
            if signal in content:
                self._found(technology, relative)

    def feed_imports(self, relative: str, imports: list[str]) -> None:
        for name in imports:
            for prefix, technology in _IMPORTS.items():
                if name == prefix or name.startswith((prefix + ".", prefix + "/")):
                    self._found(technology, relative)

    # -- output --------------------------------------------------------------------------

    def result(self) -> dict:
        architecture = []
        dirs = self.directories
        if dirs & {"controllers", "controller"} and dirs & {"models", "model", "views", "view"}:
            architecture.append("MVC")
        if dirs & {"repositories", "repository"} and dirs & {"services", "service"}:
            architecture.append("Layered (Repository/Service)")
        return {
            "languages": dict(self.extensions.most_common()),
            "technologies": [
                {"name": name, "evidence": sorted(files)}
                for name, files in sorted(self.evidence.items())
            ],
            "architecture": architecture,
        }


def _manifest_packages(name: str, content: str) -> list[str]:
    try:
        if name in ("package.json", "composer.json"):
            data = json.loads(content)
            keys = ("dependencies", "devDependencies", "require", "require-dev")
            return [package for key in keys for package in (data.get(key) or {})]
        if name == "pyproject.toml":
            data = tomllib.loads(content)
            dependencies = data.get("project", {}).get("dependencies", [])
            poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            return [_requirement_name(d) for d in dependencies] + list(poetry)
    except (ValueError, AttributeError, TypeError):
        return []
    if name in ("requirements.txt", "pipfile"):
        return [_requirement_name(line) for line in content.splitlines() if line.strip()]
    return []


def _requirement_name(line: str) -> str:
    match = _REQUIREMENT.match(line)
    return match[1].split("[")[0] if match else ""
