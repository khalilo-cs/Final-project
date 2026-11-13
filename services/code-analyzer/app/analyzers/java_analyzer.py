from tree_sitter import Node

from app.analyzers.base_analyzer import BaseAnalyzer, ClassInfo, FileAnalysis, FunctionInfo
from app.analyzers.treesitter import first_error, java_parser, line_counts, text
from app.quality.java_complexity import cognitive_complexity, cyclomatic_complexity

CLASS_TYPES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}
METHOD_TYPES = {"method_declaration", "constructor_declaration", "compact_constructor_declaration"}
_BASE_CLAUSES = {"superclass", "super_interfaces", "extends_interfaces"}
_PARAMETER_TYPES = {"formal_parameter", "spread_parameter"}


def _annotations(node: Node) -> list[str]:
    modifiers = next((c for c in node.children if c.type == "modifiers"), None)
    if modifiers is None:
        return []
    return [
        text(child.child_by_field_name("name"))
        for child in modifiers.children
        if child.type in ("annotation", "marker_annotation")
    ]


def _bases(node: Node) -> list[str]:
    bases: list[str] = []
    for clause in node.children:
        if clause.type not in _BASE_CLAUSES:
            continue
        for child in clause.named_children:
            members = child.named_children if child.type == "type_list" else [child]
            bases.extend(text(member) for member in members)
    return bases


def _member_methods(body: Node | None) -> list[str]:
    if body is None:
        return []
    members = []
    for child in body.children:
        # Enum methods sit inside an extra `enum_body_declarations` node.
        group = child.children if child.type == "enum_body_declarations" else [child]
        members.extend(text(m.child_by_field_name("name")) for m in group if m.type in METHOD_TYPES)
    return members


def _parameter_count(method: Node) -> int:
    parameters = method.child_by_field_name("parameters")
    if parameters is None:
        return 0
    return sum(1 for child in parameters.named_children if child.type in _PARAMETER_TYPES)


def _import_name(node: Node) -> str:
    value = text(node).removeprefix("import").strip().removesuffix(";").strip()
    return value.removeprefix("static ").strip()


class JavaAnalyzer(BaseAnalyzer):
    language = "java"
    extensions = (".java",)

    def analyze(self, path: str, source: str) -> FileAnalysis:
        result = FileAnalysis(path=path, language=self.language)
        tree = java_parser().parse(source.encode("utf-8", errors="replace"))
        root = tree.root_node
        (
            result.total_lines,
            result.code_lines,
            result.comment_lines,
            result.blank_lines,
        ) = line_counts(root, source, {"line_comment", "block_comment"})

        error = first_error(root)
        if error is not None:
            # tree-sitter recovers from errors, so the structure below is still useful.
            result.parse_error = (
                f"SyntaxError: invalid syntax near line {error.start_point.row + 1}"
            )

        stack: list[tuple[Node, tuple[str, ...]]] = [(root, ())]
        while stack:
            node, scope = stack.pop()
            kind = node.type
            if kind == "import_declaration":
                result.imports.append(_import_name(node))
                continue
            if kind in CLASS_TYPES:
                name = text(node.child_by_field_name("name"))
                body = node.child_by_field_name("body")
                result.classes.append(
                    ClassInfo(
                        name=".".join([*scope, name]),
                        line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        bases=_bases(node),
                        methods=_member_methods(body),
                        decorators=_annotations(node),
                    )
                )
                scope = (*scope, name)
            elif kind in METHOD_TYPES:
                name = text(node.child_by_field_name("name"))
                body = node.child_by_field_name("body")
                cognitive, nesting = cognitive_complexity(body)
                result.functions.append(
                    FunctionInfo(
                        name=name,
                        qualified_name=".".join([*scope, name]),
                        line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        parameters=_parameter_count(node),
                        cyclomatic_complexity=cyclomatic_complexity(body),
                        cognitive_complexity=cognitive,
                        max_nesting=nesting,
                        decorators=_annotations(node),
                    )
                )
                scope = (*scope, name)
            stack.extend((child, scope) for child in reversed(node.named_children))

        result.classes.sort(key=lambda c: c.line)
        result.functions.sort(key=lambda f: f.line)
        return result
