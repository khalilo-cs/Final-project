"""Cyclomatic and cognitive complexity for JavaScript/TypeScript (same rules as Java/Python)."""

from tree_sitter import Node

from app.analyzers.treesitter import walk

_LOOPS = {"for_statement", "for_in_statement", "while_statement", "do_statement"}
_LOGICAL = {"&&", "||", "??"}
_NESTING_ONLY = {
    "arrow_function", "function_expression", "function_declaration", "class_body",
    "generator_function", "generator_function_declaration", "method_definition",
}  # fmt: skip


def _operator(node: Node) -> str | None:
    operator = node.child_by_field_name("operator")
    return operator.type if operator is not None else None


def cyclomatic_complexity(body: Node | None) -> int:
    if body is None:
        return 1
    return 1 + sum(_is_decision_point(node) for node in walk(body))


_DECISIONS = _LOOPS | {"if_statement", "catch_clause", "ternary_expression", "switch_case"}


def _is_decision_point(node: Node) -> bool:
    if node.type in _DECISIONS:
        return True
    return node.type == "binary_expression" and _operator(node) in _LOGICAL


def cognitive_complexity(body: Node | None) -> tuple[int, int]:
    if body is None:
        return 0, 0
    score, max_nesting = 0, 0
    stack: list[tuple[Node, int, bool]] = [(child, 0, False) for child in body.children]

    def push(node: Node | None, nesting: int, control: bool = False) -> None:
        nonlocal max_nesting
        if node is not None:
            if control:
                max_nesting = max(max_nesting, nesting)
            stack.append((node, nesting, False))

    while stack:
        node, nesting, is_elif = stack.pop()
        kind = node.type
        if kind == "if_statement":
            score += 1 if is_elif else 1 + nesting
            push(node.child_by_field_name("condition"), nesting)
            push(node.child_by_field_name("consequence"), nesting + 1, control=True)
            alternative = node.child_by_field_name("alternative")  # an else_clause
            if alternative is not None:
                inner = next((c for c in alternative.named_children), None)
                if inner is not None and inner.type == "if_statement":
                    stack.append((inner, nesting, True))
                else:
                    score += 1
                    push(inner, nesting + 1, control=True)
            continue
        if kind in _LOOPS:
            score += 1 + nesting
            body_node = node.child_by_field_name("body")
            for child in node.children:
                push(child, nesting + 1 if child == body_node else nesting, child == body_node)
            continue
        if kind == "catch_clause":
            score += 1 + nesting
            for child in node.children:
                is_body = child.type == "statement_block"
                push(child, nesting + 1 if is_body else nesting, is_body)
            continue
        if kind == "switch_statement":
            score += 1 + nesting
            for child in node.children:
                is_body = child.type == "switch_body"
                push(child, nesting + 1 if is_body else nesting, is_body)
            continue
        if kind == "ternary_expression":
            score += 1 + nesting
        elif kind == "binary_expression":
            operator, parent = _operator(node), node.parent
            if operator in _LOGICAL and not (
                parent is not None and parent.type == "binary_expression"
                and _operator(parent) == operator
            ):  # fmt: skip
                score += 1
        elif kind in _NESTING_ONLY:
            for child in node.children:
                push(child, nesting + 1)
            continue
        for child in node.children:
            push(child, nesting)
    return score, max_nesting
