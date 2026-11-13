"""Cyclomatic and cognitive complexity for Java, over tree-sitter nodes.

Same rules as the Python implementation (complexity.py) so scores are comparable.
"""

from tree_sitter import Node

from app.analyzers.treesitter import walk

_LOOPS = {"for_statement", "enhanced_for_statement", "while_statement", "do_statement"}
_LOGICAL = {"&&", "||"}
# Bodies that add nesting without being a flow break themselves.
_NESTING_ONLY = {"lambda_expression", "class_body"}


def _operator(node: Node) -> str | None:
    operator = node.child_by_field_name("operator")
    return operator.type if operator is not None else None


def cyclomatic_complexity(body: Node | None) -> int:
    if body is None:
        return 1
    score = 1
    for node in walk(body):
        kind = node.type
        if kind in _LOOPS or kind in ("if_statement", "catch_clause", "ternary_expression") or kind == "switch_label" and node.named_child_count > 0 or kind == "binary_expression" and _operator(node) in _LOGICAL:
            score += 1
    return score


def cognitive_complexity(body: Node | None) -> tuple[int, int]:
    """Return (cognitive complexity, deepest control-flow nesting)."""
    if body is None:
        return 0, 0
    score = 0
    max_nesting = 0
    # (node, nesting level, is an `else if`)
    stack: list[tuple[Node, int, bool]] = [(child, 0, False) for child in body.children]

    def push(node: Node | None, nesting: int, control_body: bool = False) -> None:
        nonlocal max_nesting
        if node is not None:
            if control_body:
                max_nesting = max(max_nesting, nesting)
            stack.append((node, nesting, False))

    while stack:
        node, nesting, is_elif = stack.pop()
        kind = node.type

        if kind == "if_statement":
            score += 1 if is_elif else 1 + nesting
            push(node.child_by_field_name("condition"), nesting)
            push(node.child_by_field_name("consequence"), nesting + 1, control_body=True)
            alternative = node.child_by_field_name("alternative")
            if alternative is not None and alternative.type == "if_statement":
                stack.append((alternative, nesting, True))
            elif alternative is not None:
                score += 1
                push(alternative, nesting + 1, control_body=True)
            continue

        nested_child: str | None = None
        if kind in _LOOPS:
            score += 1 + nesting
            nested_child = "body"
        elif kind == "catch_clause":
            score += 1 + nesting
            nested_child = "block"
        elif kind == "switch_expression":
            score += 1 + nesting
            nested_child = "switch_block"
        elif kind == "ternary_expression":
            score += 1 + nesting
        elif kind == "binary_expression":
            operator = _operator(node)
            parent = node.parent
            # A run of the same operator (a && b && c) counts once.
            if operator in _LOGICAL and not (
                parent is not None
                and parent.type == "binary_expression"
                and _operator(parent) == operator
            ):
                score += 1
        elif kind in _NESTING_ONLY:
            for child in node.children:
                push(child, nesting + 1)
            continue

        body_node = node.child_by_field_name("body") if nested_child == "body" else None
        for child in node.children:
            is_body = (nested_child == "body" and child == body_node) or (
                nested_child is not None and nested_child != "body" and child.type == nested_child
            )
            push(child, nesting + 1 if is_body else nesting, control_body=is_body)

    return score, max_nesting
