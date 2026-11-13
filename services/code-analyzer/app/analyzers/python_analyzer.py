import ast
import io
import tokenize

from app.analyzers.base_analyzer import BaseAnalyzer, ClassInfo, FileAnalysis, FunctionInfo
from app.quality.complexity import cognitive_complexity, cyclomatic_complexity

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _name(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - unparse is total for valid trees
        return "<expr>"


def _is_generator(func: ast.AST) -> bool:
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return True
        if not isinstance(node, (*_FUNCTION_NODES, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))
    return False


def _parameter_count(func: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool) -> int:
    args = func.args
    names = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
    if is_method and names and names[0] in ("self", "cls"):
        names = names[1:]
    return len(names) + bool(args.vararg) + bool(args.kwarg)


class _Collector(ast.NodeVisitor):
    def __init__(self, result: FileAnalysis) -> None:
        self.result = result
        self.scope: list[str] = []
        self.in_class = False

    def visit_Import(self, node: ast.Import) -> None:
        self.result.imports.extend(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.result.imports.append("." * node.level + (node.module or ""))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.result.classes.append(
            ClassInfo(
                name=node.name,
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                bases=[_name(base) for base in node.bases],
                methods=[n.name for n in node.body if isinstance(n, _FUNCTION_NODES)],
                decorators=[_name(d) for d in node.decorator_list],
            )
        )
        self._descend(node, in_class=True)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        cognitive, nesting = cognitive_complexity(node)
        self.result.functions.append(
            FunctionInfo(
                name=node.name,
                qualified_name=".".join([*self.scope, node.name]),
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                parameters=_parameter_count(node, self.in_class),
                cyclomatic_complexity=cyclomatic_complexity(node),
                cognitive_complexity=cognitive,
                max_nesting=nesting,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                is_generator=_is_generator(node),
                decorators=[_name(d) for d in node.decorator_list],
            )
        )
        self._descend(node, in_class=False)

    visit_FunctionDef = visit_AsyncFunctionDef = _function

    def _descend(self, node: ast.AST, in_class: bool) -> None:
        previous = self.in_class
        self.scope.append(node.name)
        self.in_class = in_class
        self.generic_visit(node)
        self.scope.pop()
        self.in_class = previous


def _count_lines(source: str, result: FileAnalysis) -> None:
    lines = source.splitlines()
    result.total_lines = len(lines)
    result.blank_lines = sum(1 for line in lines if not line.strip())
    comment_only: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and token.line.lstrip().startswith("#"):
                comment_only.add(token.start[0])
    except (tokenize.TokenError, SyntaxError):
        comment_only = {i for i, line in enumerate(lines, 1) if line.lstrip().startswith("#")}
    result.comment_lines = len(comment_only)
    result.code_lines = result.total_lines - result.blank_lines - result.comment_lines


class PythonAnalyzer(BaseAnalyzer):
    language = "python"
    extensions = (".py",)

    def analyze(self, path: str, source: str) -> FileAnalysis:
        result = FileAnalysis(path=path, language=self.language)
        _count_lines(source, result)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError) as exc:
            result.parse_error = f"{type(exc).__name__}: {exc}"
            return result
        _Collector(result).visit(tree)
        return result
