"""The project's knowledge graph (FR-03.2) and dependency analysis (FR-03.8).

Nodes: files, classes, functions, external packages, database tables.
Edges: contains, extends / implements, calls, creates, imports, uses_table.
Names are resolved conservatively: a call is linked only when it points at one
project function without ambiguity, so the graph shows real dependencies.
"""

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass

import networkx as nx

from app.analyzers.base_analyzer import ClassInfo, FileAnalysis, FunctionInfo

# Names too generic to link a call to a project function without type information.
COMMON = {
    "get",
    "set",
    "add",
    "put",
    "remove",
    "delete",
    "size",
    "length",
    "len",
    "tostring",
    "equals",
    "hashcode",
    "print",
    "println",
    "printf",
    "append",
    "log",
    "info",
    "debug",
    "error",
    "warn",
    "format",
    "str",
    "int",
    "float",
    "map",
    "filter",
    "push",
    "pop",
    "then",
    "catch",
    "close",
    "open",
    "read",
    "write",
    "run",
    "start",
    "stop",
    "init",
    "update",
    "save",
    "load",
    "send",
    "parse",
    "join",
    "split",
    "keys",
    "values",
    "items",
    "clear",
    "contains",
    "find",
    "count",
    "next",
    "main",
    "render",
    "show",
    "setstate",
    "json",
}
MAX_VIEW_NODES = 400
_GENERIC = re.compile(r"<.*>|\[.*\]|\(.*\)")


def simple(name: str) -> str:
    name = _GENERIC.sub("", name).strip()
    return re.split(r"[.:\\]+", name)[-1] if name else ""


@dataclass
class Function:
    id: str
    file: str
    info: FunctionInfo
    owner: str | None  # class node id


@dataclass
class Klass:
    id: str
    file: str
    info: ClassInfo


class ProjectGraph:
    def __init__(self, files: list[FileAnalysis]) -> None:
        self.files = files
        self.g = nx.MultiDiGraph()
        self.classes: dict[str, Klass] = {}
        self.functions: dict[str, Function] = {}
        self.class_by_name: dict[str, list[Klass]] = defaultdict(list)
        self.function_by_name: dict[str, list[Function]] = defaultdict(list)
        self.packages: dict[str, int] = defaultdict(int)
        self._collect()
        self._link()

    # -- nodes -------------------------------------------------------------------------
    def _collect(self) -> None:
        for file in self.files:
            file_id = f"file:{file.path}"
            self.g.add_node(
                file_id,
                type="file",
                label=posixpath.basename(file.path),
                file=file.path,
                language=file.language,
                lines=file.code_lines,
            )
            for info in file.classes:
                class_id = f"class:{file.path}:{info.name}"
                klass = Klass(class_id, file.path, info)
                self.classes[class_id] = klass
                self.class_by_name[simple(info.name)].append(klass)
                self.g.add_node(
                    class_id,
                    type="class",
                    label=simple(info.name),
                    file=file.path,
                    line=info.line,
                    kind=info.kind,
                    methods=len(info.methods),
                )
                self.g.add_edge(file_id, class_id, type="contains")
            for info in file.functions:
                function_id = f"fn:{file.path}:{info.qualified_name}"
                owner = self._owner(file, info)
                function = Function(function_id, file.path, info, owner)
                self.functions[function_id] = function
                self.function_by_name[info.name.lower()].append(function)
                self.g.add_node(
                    function_id,
                    type="function",
                    label=info.name,
                    file=file.path,
                    line=info.line,
                    complexity=info.cyclomatic_complexity,
                    owner=owner,
                )
                self.g.add_edge(owner or file_id, function_id, type="contains")

    def _owner(self, file: FileAnalysis, info: FunctionInfo) -> str | None:
        prefix = info.qualified_name.rsplit(".", 1)[0] if "." in info.qualified_name else ""
        match = next((c for c in file.classes if c.name == prefix), None)
        return f"class:{file.path}:{match.name}" if match else None

    # -- edges -------------------------------------------------------------------------
    def _link(self) -> None:
        self.imports: dict[str, set[str]] = defaultdict(set)
        paths = {f.path for f in self.files}
        for file in self.files:
            submodules = [n for n in file.submodule_imports if self._import_target(file, n, paths)]
            for name in [*file.imports, *submodules]:
                target = self._import_target(file, name, paths)
                if target is not None and target != file.path:
                    self.imports[file.path].add(target)
                    self.g.add_edge(f"file:{file.path}", f"file:{target}", type="imports")
                elif target is None and (package := _package(name)):
                    self.packages[package] += 1
        for klass in self.classes.values():
            for base in klass.info.bases:
                target = self._class(simple(base), klass.file)
                if target is not None and target.id != klass.id:
                    kind = "implements" if target.info.kind == "interface" else "extends"
                    self.g.add_edge(klass.id, target.id, type=kind)
        for function in self.functions.values():
            for name in function.info.calls:
                target = self._callee(name, function)
                if target is not None:
                    self.g.add_edge(function.id, target.id, type="calls")
            for name in function.info.instantiates:
                target = self._class(simple(name), function.file)
                if target is not None:
                    self.g.add_edge(function.id, target.id, type="creates")
            for table in function.info.sql_tables:
                table_id = f"table:{table}"
                self.g.add_node(table_id, type="table", label=table)
                self.g.add_edge(function.id, table_id, type="uses_table")

    def _class(self, name: str, near: str) -> Klass | None:
        candidates = self.class_by_name.get(name, [])
        if len(candidates) == 1:
            return candidates[0]
        same_file = [c for c in candidates if c.file == near]
        return same_file[0] if len(same_file) == 1 else None

    def _callee(self, call: str, caller: Function) -> Function | None:
        receiver, _, name = call.rpartition(".")
        candidates = [c for c in self.function_by_name.get(name.lower(), []) if c.id != caller.id]
        if not candidates:
            return None
        if receiver in ("self", "this", "cls", "super", "base"):
            family = self._family(caller.owner)
            close = [c for c in candidates if c.owner in family]
            return close[0] if len(close) == 1 or (close and receiver != "super") else None
        if receiver and (klass := self._class(receiver, caller.file)) is not None:
            static = [c for c in candidates if c.owner == klass.id]  # Database.getInstance()
            if len(static) == 1:
                return static[0]
        created = {
            k.id for n in caller.info.instantiates if (k := self._class(simple(n), caller.file))
        }
        imported = self.imports.get(caller.file, set())
        scopes = [
            lambda c: c.owner is not None and c.owner == caller.owner,  # same class
            lambda c: c.owner in created,  # an object the caller creates
            lambda c: c.file == caller.file,
            lambda c: c.file in imported,
        ]
        if receiver:  # repository.save() -> a class whose name contains "repository"
            scopes.append(lambda c: c.owner is not None and receiver.lower().lstrip("_")
                          in self.g.nodes[c.owner]["label"].lower())  # fmt: skip
        else:
            scopes = [scopes[0], scopes[2], scopes[3]]
        for scope in scopes:
            close = [c for c in candidates if scope(c)]
            if len(close) == 1:
                return close[0]
        # A plain call with one possible target (never a member call on an unknown object:
        # it is more likely a library method with the same name).
        plain = [c for c in candidates if c.owner is None]
        if not receiver and len(plain) == 1 and name.lower() not in COMMON:
            return plain[0]
        return None

    def _family(self, class_id: str | None) -> set[str]:
        """The class and its project ancestors."""
        family, todo = set(), [class_id] if class_id else []
        while todo:
            current = todo.pop()
            if current in family:
                continue
            family.add(current)
            todo.extend(v for _, v, k in self.g.out_edges(current, data="type")
                        if k in ("extends", "implements"))  # fmt: skip
        return family

    def _import_target(self, file: FileAnalysis, name: str, paths: set[str]) -> str | None:
        here = posixpath.dirname(file.path)
        if file.language == "python":
            level = len(name) - len(name.lstrip("."))
            module = name.lstrip(".").replace(".", "/")
            base = here
            for _ in range(max(level - 1, 0)):
                base = posixpath.dirname(base)
            stems = [posixpath.join(base, module)] if level else [module]
            for stem in stems:
                for candidate in (f"{stem}.py", f"{stem}/__init__.py"):
                    found = _by_suffix(candidate.lstrip("/"), paths, file.path)
                    if found:
                        return found
            return None
        if name.startswith("."):  # JS/TS relative import
            stem = posixpath.normpath(posixpath.join(here, name))
            for ext in ("", ".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.ts", "/index.tsx"):
                if f"{stem}{ext}" in paths:
                    return f"{stem}{ext}"
            return None
        if file.language in ("cpp", "c"):
            return _by_suffix(name, paths, file.path)
        # Java / C#: import a class -> the file that declares it
        klass = self._class(simple(name), file.path)
        return klass.file if klass is not None else None


def _by_suffix(relative: str, paths: set[str], near: str) -> str | None:
    """The matching file closest to `near` (a monorepo has many app/config.py)."""
    matches = [p for p in paths if p == relative or p.endswith("/" + relative)]
    if not matches:
        return None
    return max(matches, key=lambda p: (len(posixpath.commonpath([p, near]) if "/" in near
                                           and "/" in p else ""), -len(p)))  # fmt: skip


def _package(name: str) -> str:
    name = name.strip().lstrip("@")
    if not name or name.startswith((".", "/")):
        return ""
    if name.startswith("java.") or name.startswith("System"):
        return ""  # the language's own library
    return re.split(r"[./:]", name)[0]
