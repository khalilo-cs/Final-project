"""Propose fixes for a project and apply the ones the student approved."""

import ast
import io
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

from app.fixes.java_fixes import propose_java
from app.fixes.models import Fix, apply_edits
from app.fixes.python_fixes import propose_python
from app.security.python_rules import scan_python
from app.services.project_analyzer import MAX_FILE_BYTES, _project_files

_PROPOSERS = {".py": propose_python, ".java": propose_java}


def _sources(root: Path):
    for path, relative in _project_files(root):
        proposer = _PROPOSERS.get(path.suffix.lower())
        if proposer and path.stat().st_size <= MAX_FILE_BYTES:
            yield relative, path.read_text(encoding="utf-8", errors="replace"), proposer


def propose(root: Path) -> list[dict]:
    fixes = []
    for relative, source, proposer in _sources(root):
        fixes += [fix.as_dict(source) for fix in proposer(relative, source)]
    return sorted(fixes, key=lambda f: (f["kind"] != "patch", f["file"], f["line"]))


def _validate(relative: str, before: str, after: str, fixes: list[Fix]) -> str | None:
    """None if the new file is valid and the fixed findings are really gone."""
    try:
        ast.parse(after)
    except SyntaxError as exc:
        return f"the result would not be valid Python ({exc.msg})"
    remaining = Counter(v.type for v in scan_python(relative, after))
    original = Counter(v.type for v in scan_python(relative, before))
    for kind, count in Counter(f.type for f in fixes).items():
        if kind in original and remaining[kind] > max(0, original[kind] - count):
            return f"the {kind} finding would still be reported"
    return None


def apply(root: Path, archive: Path, fix_ids: list[str]) -> tuple[bytes, list, list]:
    wanted = set(fix_ids)
    changed: dict[str, str] = {}
    applied, skipped = [], []
    found: set[str] = set()
    for relative, source, proposer in _sources(root):
        fixes = [f for f in proposer(relative, source) if f.id in wanted]
        found |= {f.id for f in fixes}
        patches = [f for f in fixes if f.kind == "patch"]
        skipped += [{"id": f.id, "reason": "advice only, change it by hand"} for f in fixes
                    if f.kind != "patch"]  # fmt: skip
        if not patches:
            continue
        edits = [edit for fix in patches for edit in fix.edits]
        imports = {fix.add_import for fix in patches if fix.add_import}
        after = apply_edits(source, edits)
        for statement in sorted(imports):
            after = apply_edits(after, [], statement)
        problem = _validate(relative, source, after, patches) if relative.endswith(".py") else None
        if problem:
            skipped += [{"id": f.id, "reason": problem} for f in patches]
            continue
        changed[relative] = after
        applied += [{"id": f.id, "file": f.file, "line": f.line, "type": f.type,
                     "title": f.title} for f in patches]  # fmt: skip
    skipped += [{"id": i, "reason": "fix no longer applies"} for i in sorted(wanted - found)]
    return _rebuild(archive, changed), applied, skipped


def _rebuild(archive: Path, changed: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with (
        zipfile.ZipFile(archive) as source,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for info in source.infolist():
            name = PurePosixPath(info.filename).as_posix()
            if name in changed:
                target.writestr(info, changed[name].encode("utf-8"))
            else:
                target.writestr(info, source.read(info))
    return output.getvalue()
