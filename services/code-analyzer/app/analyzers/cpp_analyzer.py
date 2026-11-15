from pathlib import PurePosixPath

from tree_sitter import Node

from app.analyzers.base_analyzer import BaseAnalyzer, ClassInfo, FileAnalysis, FunctionInfo
from app.analyzers.facts import ts_facts
from app.analyzers.treesitter import cpp_parser, first_error, line_counts, text
from app.quality.ts_complexity import CPP, cognitive_complexity, cyclomatic_complexity

CLASS_TYPES = {"class_specifier", "struct_specifier", "union_specifier"}
_NAME_TYPES = {
    "identifier",
    "field_identifier",
    "qualified_identifier",
    "destructor_name",
    "operator_name",
    "template_function",
}
C_EXTENSIONS = (".c",)


def function_declarator(node: Node) -> Node | None:
    """Unwrap pointer/reference declarators down to the function_declarator."""
    current = node.child_by_field_name("declarator")
    while current is not None and current.type != "function_declarator":
        current = current.child_by_field_name("declarator")
    return current


def function_name(node: Node) -> tuple[str, str]:
    """(short name, qualified name as written) of a function_definition."""
    declarator = function_declarator(node)
    target = declarator.child_by_field_name("declarator") if declarator is not None else None
    if target is None or target.type not in _NAME_TYPES:
        return "<anonymous>", "<anonymous>"
    written = text(target)
    if target.type == "qualified_identifier":
        name = written.rsplit("::", 1)[-1]
        return name, written.replace("::", ".")
    return written, written


def _parameters(node: Node) -> int:
    declarator = function_declarator(node)
    parameters = declarator.child_by_field_name("parameters") if declarator else None
    if parameters is None:
        return 0
    params = [c for c in parameters.named_children if c.type.endswith("parameter_declaration")]
    # f(void) takes nothing.
    if len(params) == 1 and text(params[0]).strip() == "void":
        return 0
    return len(params)


def _bases(node: Node) -> list[str]:
    clause = next((c for c in node.children if c.type == "base_class_clause"), None)
    if clause is None:
        return []
    return [text(c) for c in clause.named_children if c.type != "access_specifier"]


def _methods(body: Node | None) -> list[str]:
    if body is None:
        return []
    names = []
    for child in body.named_children:
        if child.type == "template_declaration":
            child = next(
                (c for c in child.named_children if c.type == "function_definition"), child
            )
        if child.type == "function_definition" or (
            child.type in ("field_declaration", "declaration") and function_declarator(child)
        ):
            names.append(function_name(child)[0])
    return names


def _include(node: Node) -> str:
    return text(node.child_by_field_name("path")).strip('<>"')


class CppAnalyzer(BaseAnalyzer):
    language = "cpp"
    extensions = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h", ".c")

    def analyze(self, path: str, source: str) -> FileAnalysis:
        language = "c" if PurePosixPath(path).suffix.lower() in C_EXTENSIONS else "cpp"
        result = FileAnalysis(path=path, language=language)
        root = cpp_parser().parse(source.encode("utf-8", errors="replace")).root_node
        (
            result.total_lines,
            result.code_lines,
            result.comment_lines,
            result.blank_lines,
        ) = line_counts(root, source, {"comment"})
        error = first_error(root)
        if error is not None:
            result.parse_error = (
                f"SyntaxError: invalid syntax near line {error.start_point.row + 1}"
            )

        stack: list[tuple[Node, tuple[str, ...]]] = [(root, ())]
        while stack:
            node, scope = stack.pop()
            kind = node.type
            if kind == "preproc_include":
                result.imports.append(_include(node))
                continue
            body = node.child_by_field_name("body")
            if kind in CLASS_TYPES and body is not None:
                name = text(node.child_by_field_name("name")) or "<anonymous>"
                result.classes.append(
                    ClassInfo(
                        name=".".join([*scope, name]),
                        line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        bases=_bases(node),
                        methods=_methods(body),
                        kind="struct" if kind == "struct_specifier" else "class",
                    )
                )
                scope = (*scope, name)
            elif kind == "function_definition":
                name, written = function_name(node)
                cognitive, nesting = cognitive_complexity(body, CPP)
                qualified = ".".join([*scope, written])
                result.functions.append(
                    FunctionInfo(
                        name=name,
                        qualified_name=qualified,
                        line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        parameters=_parameters(node),
                        cyclomatic_complexity=cyclomatic_complexity(body, CPP),
                        cognitive_complexity=cognitive,
                        max_nesting=nesting,
                    )
                )
                ts_facts(result.functions[-1], body)
                scope = (*scope, name)
            stack.extend((child, scope) for child in reversed(node.named_children))

        result.classes.sort(key=lambda c: c.line)
        result.functions.sort(key=lambda f: f.line)
        return result
