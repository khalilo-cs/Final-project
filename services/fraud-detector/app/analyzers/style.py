"""Coding style consistency (FR-08.6): files written very differently stand out."""

import re
from collections import Counter, defaultdict
from pathlib import Path

from app.analyzers.tokens import IGNORED_PATH_PARTS, KEYWORDS, SOURCE_EXTENSIONS

MIN_LINES = 20
_GROUPS = {".py": "python", ".java": "c", ".js": "js", ".jsx": "js", ".ts": "js", ".tsx": "js",
           ".php": "c", ".cs": "c", ".cpp": "c", ".cc": "c", ".c": "c", ".h": "c", ".hpp": "c",
           ".kt": "c", ".dart": "c", ".go": "c", ".rb": "python", ".swift": "c"}  # fmt: skip
_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
_STRING = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'")


def file_style(source: str, group: str) -> dict:
    lines = source.splitlines()
    code = [line for line in lines if line.strip()]
    indents = Counter()
    for line in code:
        leading = line[: len(line) - len(line.lstrip())]
        if leading.startswith("\t"):
            indents["tab"] += 1
        elif leading:
            width = len(leading)
            indents["2" if width % 4 else "4"] += 1
    names = [n for n in _IDENTIFIER.findall(_STRING.sub("", source)) if n not in KEYWORDS]
    snake = sum(1 for n in names if "_" in n.strip("_") and n.islower())
    camel = sum(1 for n in names if re.search(r"[a-z][A-Z]", n))
    comment_marks = ("#",) if group == "python" else ("//", "/*", "*")
    comments = sum(1 for line in code if line.lstrip().startswith(comment_marks))
    single = source.count("'")
    double = source.count('"')
    style = {
        "indent": indents.most_common(1)[0][0] if indents else None,
        "naming": None if snake + camel < 5 else "snake" if snake > 2 * camel
        else "camel" if camel > 2 * snake else "mixed",
        "comments": "none" if not comments else "heavy" if comments / len(code) > 0.25 else "some",
        "quotes": None if single + double < 6 else "single" if single > 2 * double
        else "double" if double > 2 * single else "mixed",
    }  # fmt: skip
    if group != "python":
        same_line = sum(1 for line in code if line.rstrip().endswith("{") and line.strip() != "{")
        own_line = sum(1 for line in code if line.strip() == "{")
        if same_line + own_line >= 3:
            style["braces"] = "same_line" if same_line >= own_line else "own_line"
    return style


def analyze_style(root: Path) -> dict:
    files: dict[str, list[tuple[str, int, dict]]] = defaultdict(list)
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        group = _GROUPS.get(path.suffix.lower())
        if group is None or path.is_symlink() or not path.is_file():
            continue
        if (
            set(relative.parts[:-1]) & IGNORED_PATH_PARTS
            or path.suffix.lower() not in SOURCE_EXTENSIONS
        ):
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        size = sum(1 for line in source.splitlines() if line.strip())
        if size >= MIN_LINES:
            files[group].append((relative.as_posix(), size, file_style(source, group)))

    outliers, total_lines, outlier_lines = [], 0, 0
    dominant_by_group = {}
    for group, entries in files.items():
        total_lines += sum(size for _, size, _ in entries)
        if len(entries) < 3:
            continue
        features = {k for _, _, style in entries for k in style}
        dominant = {}
        for feature in features:
            values = Counter(s[feature] for _, _, s in entries if s.get(feature))
            if values:
                value, count = values.most_common(1)[0]
                if count / len(entries) >= 0.6:  # only a clear house style counts
                    dominant[feature] = value
        dominant_by_group[group] = dominant
        for path, size, style in entries:
            differs = {f: {"file": style[f], "project": v} for f, v in dominant.items()
                       if style.get(f) and style[f] != v}  # fmt: skip
            if len(differs) >= 2:
                outliers.append({"file": path, "lines": size, "differs": differs})
                outlier_lines += size
    score = round(100 * (1 - outlier_lines / total_lines), 1) if total_lines else None
    return {
        "files_compared": sum(len(e) for e in files.values()),
        "project_style": dominant_by_group,
        "outliers": outliers,
        "style_consistency_score": score,
    }
