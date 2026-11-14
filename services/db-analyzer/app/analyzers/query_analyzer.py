"""Issues in SQL queries found in the uploaded file (FR-05.5)."""

from app.analyzers.issues import Issue, Severity
from app.parsers.schema import Schema


def analyze_queries(schema: Schema) -> list[Issue]:
    issues = []
    for query in schema.queries:
        if query.kind in ("UPDATE", "DELETE") and not query.has_where:
            issues.append(
                Issue(
                    f"{query.kind.lower()}_without_where",
                    Severity.high,
                    "",
                    f"{query.kind} without WHERE affects every row: {query.sql}",
                    line=query.line,
                )
            )
        if query.selects_star:
            issues.append(
                Issue(
                    "select_star",
                    Severity.low,
                    "",
                    f"SELECT * fetches every column and breaks when columns change: {query.sql}",
                    line=query.line,
                    suggestion="List the columns you need",
                )
            )
    return issues
