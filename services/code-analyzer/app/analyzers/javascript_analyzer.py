from tree_sitter import Node

from app.analyzers.base_analyzer import BaseAnalyzer, ClassInfo, FileAnalysis, FunctionInfo
from app.analyzers.facts import ts_facts
from app.analyzers.treesitter import first_error, js_parser, line_counts, text
from app.quality.js_complexity import cognitive_complexity, cyclomatic_complexity

_FUNCTION_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}
_PARAMETERS = {"identifier", "assignment_pattern", "rest_pattern", "object_pattern",
               "array_pattern", "required_parameter", "optional_parameter"}  # fmt: skip
_CLASSES = {"class_declaration", "class", "abstract_class_declaration", "interface_declaration"}
_CLASS_KINDS = {"abstract_class_declaration": "abstract", "interface_declaration": "interface"}


def dialect_for(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".tsx"):
        return "tsx"
    if lowered.endswith(".ts"):
        return "typescript"
    return "javascript"


def _parameters(function: Node) -> int:
    params = function.child_by_field_name("parameters")
    if params is None:
        single = function.child_by_field_name("parameter")  # x => x * 2
        return 1 if single is not None else 0
    return sum(1 for c in params.named_children if c.type in _PARAMETERS)


def _bases(heritage: Node | None) -> list[str]:
    """JS: `extends Base`; TS wraps it: extends_clause / implements_clause."""
    if heritage is None:
        return []
    bases = []
    for child in heritage.named_children:
        if child.type in ("extends_clause", "implements_clause"):
            bases.extend(text(c) for c in child.named_children)
        else:
            bases.append(text(child))
    return bases


def _is_async(function: Node) -> bool:
    return any(child.type == "async" for child in function.children)


class JavaScriptAnalyzer(BaseAnalyzer):
    language = "javascript"
    extensions = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

    def analyze(self, path: str, source: str) -> FileAnalysis:
        dialect = dialect_for(path)
        language = "typescript" if dialect != "javascript" else "javascript"
        result = FileAnalysis(path=path, language=language)
        root = js_parser(dialect).parse(source.encode("utf-8", errors="replace")).root_node
        (
            result.total_lines,
            result.code_lines,
            result.comment_lines,
            result.blank_lines,
        ) = line_counts(root, source, {"comment"})
        if (error := first_error(root)) is not None:
            result.parse_error = (
                f"SyntaxError: invalid syntax near line {error.start_point.row + 1}"
            )

        stack: list[tuple[Node, tuple[str, ...]]] = [(root, ())]
        while stack:
            node, scope = stack.pop()
            kind = node.type
            name, function = None, None
            if kind == "import_statement":
                source_node = node.child_by_field_name("source")
                result.imports.append(text(source_node).strip("'\"`"))
            elif (
                kind == "call_expression"
                and text(node.child_by_field_name("function")) == "require"
            ):
                arguments = node.child_by_field_name("arguments")
                if arguments is not None and arguments.named_children:
                    result.imports.append(text(arguments.named_children[0]).strip("'\"`"))
            elif kind in _CLASSES:
                class_name = text(node.child_by_field_name("name")) or "(anonymous)"
                body = node.child_by_field_name("body")
                heritage = next((c for c in node.children if c.type == "class_heritage"), None)
                result.classes.append(
                    ClassInfo(
                        name=".".join([*scope, class_name]),
                        line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        bases=_bases(heritage),
                        methods=[
                            text(m.child_by_field_name("name"))
                            for m in (body.named_children if body else [])
                            if m.type in ("method_definition", "method_signature")
                        ],
                        kind=_CLASS_KINDS.get(kind, "class"),
                    )
                )
                scope = (*scope, class_name)
            elif kind in ("function_declaration", "generator_function_declaration",
                          "method_definition"):  # fmt: skip
                name, function = text(node.child_by_field_name("name")), node
            elif kind == "variable_declarator":
                value = node.child_by_field_name("value")
                if value is not None and value.type in _FUNCTION_VALUES:
                    name, function = text(node.child_by_field_name("name")), value

            if function is not None:
                body = function.child_by_field_name("body")
                cognitive, nesting = cognitive_complexity(body)
                result.functions.append(
                    FunctionInfo(
                        name=name,
                        qualified_name=".".join([*scope, name]),
                        line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        parameters=_parameters(function),
                        cyclomatic_complexity=cyclomatic_complexity(body),
                        cognitive_complexity=cognitive,
                        max_nesting=nesting,
                        is_async=_is_async(function),
                    )
                )
                ts_facts(result.functions[-1], body)
                scope = (*scope, name)
                if function is not node:  # const f = () => ...: descend into the function
                    stack.append((function, scope))
                    continue
            stack.extend((child, scope) for child in reversed(node.named_children))

        result.classes.sort(key=lambda c: c.line)
        result.functions.sort(key=lambda f: f.line)
        return result
