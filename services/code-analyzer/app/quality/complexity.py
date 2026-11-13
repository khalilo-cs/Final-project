"""Cyclomatic and cognitive complexity for Python functions."""

import ast

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_LOOPS = (ast.For, ast.AsyncFor, ast.While)


def cyclomatic_complexity(func: ast.AST) -> int:
    """McCabe complexity: 1 + number of decision points (nested functions included)."""
    score = 1
    for node in ast.walk(func):
        if isinstance(node, (ast.If, ast.IfExp, ast.ExceptHandler, ast.Assert, *_LOOPS)):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
        elif isinstance(node, ast.match_case):
            score += 1
    return score


class _CognitiveVisitor(ast.NodeVisitor):
    """Simplified SonarSource cognitive complexity.

    Every break in linear flow costs 1, plus 1 per level of nesting it sits in.
    `elif` / `else` and boolean operator sequences cost a flat 1.
    """

    def __init__(self) -> None:
        self.score = 0
        self.nesting = 0
        self.max_nesting = 0

    def _nested(self, nodes: list[ast.stmt]) -> None:
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        for node in nodes:
            self.visit(node)
        self.nesting -= 1

    def visit_If(self, node: ast.If, is_elif: bool = False) -> None:
        self.score += 1 if is_elif else 1 + self.nesting
        self.visit(node.test)
        self._nested(node.body)
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            self.visit_If(node.orelse[0], is_elif=True)
        elif node.orelse:
            self.score += 1
            self._nested(node.orelse)

    def _loop(self, node: ast.For | ast.AsyncFor | ast.While) -> None:
        self.score += 1 + self.nesting
        self.visit(node.test if isinstance(node, ast.While) else node.iter)
        self._nested(node.body)
        self._nested(node.orelse)

    visit_For = visit_AsyncFor = visit_While = _loop

    def _try(self, node: ast.Try) -> None:
        for stmt in node.body:
            self.visit(stmt)
        for handler in node.handlers:
            self.score += 1 + self.nesting
            self._nested(handler.body)
        for stmt in node.orelse + node.finalbody:
            self.visit(stmt)

    visit_Try = visit_TryStar = _try

    def visit_Match(self, node: ast.Match) -> None:
        self.score += 1 + self.nesting
        for case in node.cases:
            self._nested(case.body)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.score += 1 + self.nesting
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.score += 1
        self.generic_visit(node)

    def _function(self, node: ast.AST) -> None:
        # A nested function adds nesting but is not itself a flow break.
        self.nesting += 1
        self.generic_visit(node)
        self.nesting -= 1

    visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _function


def cognitive_complexity(func: ast.AST) -> tuple[int, int]:
    """Return (cognitive complexity, deepest control-flow nesting) of a function."""
    visitor = _CognitiveVisitor()
    body = func.body if isinstance(func.body, list) else [func.body]
    for stmt in body:
        visitor.visit(stmt)
    return visitor.score, visitor.max_nesting
