"""What viva-engine needs to know about a project to ask about the student's own code."""

import zipfile
from pathlib import Path, PurePosixPath

from app.models.project import Project
from app.services.grading import ProjectResults

MAX_SNIPPET_LINES = 40


def _snippets(code_path: str, wanted: dict[str, list[tuple[int, int]]]) -> dict:
    found = {}
    try:
        with zipfile.ZipFile(Path(code_path)) as bundle:
            names = {PurePosixPath(n).as_posix(): n for n in bundle.namelist()}
            for file, ranges in wanted.items():
                member = names.get(file)
                if member is None or bundle.getinfo(member).file_size > 1_000_000:
                    continue
                lines = bundle.read(member).decode("utf-8", errors="replace").splitlines()
                for start, end in ranges:
                    end = min(end, start + MAX_SNIPPET_LINES - 1)
                    found[(file, start)] = "\n".join(lines[start - 1 : end])
    except (OSError, zipfile.BadZipFile):
        pass
    return found


def build_context(project: Project, results: ProjectResults) -> dict:
    context: dict = {"title": project.title}
    if results.code:
        stack = results.code.stack or {}
        context["languages"] = stack.get("languages", {})
        context["technologies"] = [t["name"] for t in stack.get("technologies", [])]
        context["architecture"] = stack.get("architecture", [])
        functions = []
        for file in results.code.details.get("files", []):
            for function in file.get("functions", []):
                functions.append({**function, "file": file["path"]})
        # The most complex functions are the ones only the author can explain.
        functions.sort(key=lambda f: f["cyclomatic_complexity"], reverse=True)
        chosen = [f for f in functions if f["end_line"] - f["line"] >= 3][:5]
        wanted: dict = {}
        for f in chosen:
            wanted.setdefault(f["file"], []).append((f["line"], f["end_line"]))
        snippets = _snippets(project.code_path, wanted)
        context["functions"] = [
            {
                "file": f["file"],
                "function": f["qualified_name"],
                "line": f["line"],
                "end_line": f["end_line"],
                "cyclomatic_complexity": f["cyclomatic_complexity"],
                "code": snippets.get((f["file"], f["line"])),
            }
            for f in chosen
        ]
    if results.security:
        context["vulnerabilities"] = [
            {k: v[k] for k in ("type", "file", "line", "evidence") if k in v}
            for v in results.security.vulnerabilities[:5]
        ]
    if results.database:
        details = results.database.details
        context["database"] = {
            "tables": [
                {
                    "name": t["name"],
                    "primary_key": t["primary_key"],
                    "foreign_keys": [
                        {"columns": fk["columns"], "ref_table": fk["ref_table"]}
                        for fk in t["foreign_keys"]
                    ],
                }
                for t in details.get("tables", [])[:15]
            ],
            "normalization_level": results.database.normalization_level,
            "issues": [
                {k: i.get(k) for k in ("type", "table", "columns", "message")}
                for i in details.get("issues", [])[:5]
            ],
        }
    if results.report:
        context["report"] = {"inconsistencies": results.report.inconsistencies[:3]}
    return context
