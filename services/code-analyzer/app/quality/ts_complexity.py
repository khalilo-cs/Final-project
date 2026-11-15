"""Cyclomatic and cognitive complexity over any tree-sitter grammar.

Same rules as the Python/Java implementations so scores stay comparable between
languages; each grammar only supplies its node names (`ComplexitySpec`).
"""

from dataclasses import dataclass

from tree_sitter import Node

from app.analyzers.treesitter import walk


@dataclass(frozen=True)
class ComplexitySpec:
    loops: frozenset[str]
    catches: frozenset[str]
    switches: frozenset[str]
    cases: frozenset[str]  # a case counts unless it is `default`
    ternaries: frozenset[str]
    logical: frozenset[str]
    nesting_only: frozenset[str]  # lambdas, local functions, nested classes
    else_wrapper: str | None = None  # C++ wraps the else branch in `else_clause`


def _operator(node: Node) -> str | None:
    operator = node.child_by_field_name("operator")
    return operator.type if operator is not None else None


def _is_case(node: Node, spec: ComplexitySpec) -> bool:
    return node.type in spec.cases and not any(c.type == "default" for c in node.children)


def _is_decision_point(node: Node, spec: ComplexitySpec) -> bool:
    kind = node.type
    if kind in spec.loops or kind in spec.catches or kind in spec.ternaries:
        return True
    if kind == "if_statement":
        return True
    if kind in spec.cases:
        return _is_case(node, spec)
    return kind == "binary_expression" and _operator(node) in spec.logical


def cyclomatic_complexity(body: Node | None, spec: ComplexitySpec) -> int:
    if body is None:
        return 1
    return 1 + sum(_is_decision_point(node, spec) for node in walk(body))


def _starts_logical_run(node: Node, spec: ComplexitySpec) -> bool:
    """`a && b && c` counts once."""
    operator = _operator(node)
    if operator not in spec.logical:
        return False
    parent = node.parent
    return not (
        parent is not None and parent.type == "binary_expression" and _operator(parent) == operator
    )


def cognitive_complexity(body: Node | None, spec: ComplexitySpec) -> tuple[int, int]:
    """Return (cognitive complexity, deepest control-flow nesting)."""
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

    def push_with_body(node: Node, nesting: int) -> None:
        body_node = node.child_by_field_name("body")
        for child in node.children:
            is_body = child == body_node
            push(child, nesting + 1 if is_body else nesting, is_body)

    while stack:
        node, nesting, is_elif = stack.pop()
        kind = node.type
        if kind == "if_statement":
            score += 1 if is_elif else 1 + nesting
            push(node.child_by_field_name("condition"), nesting)
            push(node.child_by_field_name("consequence"), nesting + 1, control=True)
            alternative = node.child_by_field_name("alternative")
            if alternative is not None and alternative.type == spec.else_wrapper:
                alternative = next(iter(alternative.named_children), None)
            if alternative is not None and alternative.type == "if_statement":
                stack.append((alternative, nesting, True))
            elif alternative is not None:
                score += 1
                push(alternative, nesting + 1, control=True)
        elif kind in spec.loops or kind in spec.catches or kind in spec.switches:
            score += 1 + nesting
            push_with_body(node, nesting)
        elif kind in spec.nesting_only:
            for child in node.children:
                push(child, nesting + 1)
        else:
            if kind in spec.ternaries:
                score += 1 + nesting
            elif kind == "binary_expression" and _starts_logical_run(node, spec):
                score += 1
            for child in node.children:
                push(child, nesting)
    return score, max_nesting


CSHARP = ComplexitySpec(
    loops=frozenset({"for_statement", "foreach_statement", "while_statement", "do_statement"}),
    catches=frozenset({"catch_clause"}),
    switches=frozenset({"switch_statement", "switch_expression"}),
    cases=frozenset({"switch_section", "switch_expression_arm"}),
    ternaries=frozenset({"conditional_expression"}),
    logical=frozenset({"&&", "||", "??"}),
    nesting_only=frozenset(
        {
            "lambda_expression",
            "anonymous_method_expression",
            "local_function_statement",
            "declaration_list",
        }
    ),
)

CPP = ComplexitySpec(
    loops=frozenset({"for_statement", "for_range_loop", "while_statement", "do_statement"}),
    catches=frozenset({"catch_clause"}),
    switches=frozenset({"switch_statement"}),
    cases=frozenset({"case_statement"}),
    ternaries=frozenset({"conditional_expression"}),
    logical=frozenset({"&&", "||", "and", "or"}),
    nesting_only=frozenset({"lambda_expression", "field_declaration_list"}),
    else_wrapper="else_clause",
)
