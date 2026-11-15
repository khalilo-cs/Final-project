from tree_sitter import Node

from app.analyzers.base_analyzer import BaseAnalyzer, ClassInfo, FileAnalysis, FunctionInfo
from app.analyzers.treesitter import csharp_parser, first_error, line_counts, text
from app.quality.ts_complexity import CSHARP, cognitive_complexity, cyclomatic_complexity

CLASS_TYPES = {
    "class_declaration",
    "interface_declaration",
    "struct_declaration",
    "enum_declaration",
    "record_declaration",
    "record_struct_declaration",
}
METHOD_TYPES = {
    "method_declaration",
    "constructor_declaration",
    "destructor_declaration",
    "local_function_statement",
    "operator_declaration",
}


def _attributes(node: Node) -> list[str]:
    return [
        text(attribute.child_by_field_name("name"))
        for group in node.children
        if group.type == "attribute_list"
        for attribute in group.named_children
        if attribute.type == "attribute"
    ]


def _modifiers(node: Node) -> set[str]:
    return {text(child) for child in node.children if child.type == "modifier"}


def _bases(node: Node) -> list[str]:
    base_list = next((c for c in node.children if c.type == "base_list"), None)
    if base_list is None:
        return []
    return [text(c) for c in base_list.named_children if c.type != "argument_list"]


def _methods(body: Node | None) -> list[str]:
    if body is None:
        return []
    return [
        text(c.child_by_field_name("name")) for c in body.named_children if c.type in METHOD_TYPES
    ]


def _parameters(method: Node) -> int:
    parameters = method.child_by_field_name("parameters")
    if parameters is None:
        return 0
    return sum(1 for c in parameters.named_children if c.type == "parameter")


def _using(node: Node) -> str | None:
    names = [c for c in node.named_children if c.type in ("qualified_name", "identifier")]
    return text(names[-1]) if names else None


class CSharpAnalyzer(BaseAnalyzer):
    language = "csharp"
    extensions = (".cs",)

    def analyze(self, path: str, source: str) -> FileAnalysis:
        result = FileAnalysis(path=path, language=self.language)
        root = csharp_parser().parse(source.encode("utf-8", errors="replace")).root_node
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
            if kind == "using_directive":
                if (name := _using(node)) is not None:
                    result.imports.append(name)
                continue
            if kind in CLASS_TYPES:
                name = text(node.child_by_field_name("name"))
                result.classes.append(
                    ClassInfo(
                        name=".".join([*scope, name]),
                        line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        bases=_bases(node),
                        methods=_methods(node.child_by_field_name("body")),
                        decorators=_attributes(node),
                    )
                )
                scope = (*scope, name)
            elif kind in METHOD_TYPES:
                name = text(node.child_by_field_name("name")) or kind.split("_")[0]
                body = node.child_by_field_name("body")
                cognitive, nesting = cognitive_complexity(body, CSHARP)
                result.functions.append(
                    FunctionInfo(
                        name=name,
                        qualified_name=".".join([*scope, name]),
                        line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        parameters=_parameters(node),
                        cyclomatic_complexity=cyclomatic_complexity(body, CSHARP),
                        cognitive_complexity=cognitive,
                        max_nesting=nesting,
                        is_async="async" in _modifiers(node),
                        decorators=_attributes(node),
                    )
                )
                scope = (*scope, name)
            stack.extend((child, scope) for child in reversed(node.named_children))

        result.classes.sort(key=lambda c: c.line)
        result.functions.sort(key=lambda f: f.line)
        return result
