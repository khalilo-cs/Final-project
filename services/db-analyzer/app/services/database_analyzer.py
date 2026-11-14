from collections import Counter
from dataclasses import asdict

from app.analyzers.er_generator import generate_er_diagram
from app.analyzers.issues import Issue, Severity
from app.analyzers.key_analyzer import analyze_indexes, analyze_keys
from app.analyzers.normalization import analyze_normalization
from app.analyzers.query_analyzer import analyze_queries
from app.analyzers.type_checker import check_types
from app.parsers.schema_parser import parse_schema

# Starting weights, to be tuned against faculty grades later.
_PENALTY = {Severity.critical: 20, Severity.high: 10, Severity.medium: 5, Severity.low: 1}


def _score(issues: list[Issue], table_count: int) -> float:
    if table_count == 0:
        return 0.0
    penalty = sum(_PENALTY[issue.severity] for issue in issues)
    # Larger schemas get proportionally more room for mistakes.
    scale = max(1.0, table_count / 5)
    return round(max(0.0, 100 - penalty / scale), 1)


def analyze_database(sql: str, dialect: str = "mysql") -> dict:
    schema = parse_schema(sql, dialect)
    key_issues = analyze_keys(schema)
    index_issues = analyze_indexes(schema)
    level, normalization_issues = analyze_normalization(schema)
    type_issues = check_types(schema)
    query_issues = analyze_queries(schema)
    issues = key_issues + index_issues + normalization_issues + type_issues + query_issues

    tables = schema.tables.values()
    return {
        "dialect": dialect,
        "total_tables": len(schema.tables),
        "total_columns": sum(len(t.columns) for t in tables),
        "total_foreign_keys": sum(len(t.foreign_keys) for t in tables),
        "normalization_level": level,
        "normalization_note": (
            "Estimated from column names and keys; functional dependencies cannot be "
            "proven from a schema alone."
        ),
        "missing_primary_keys": [i.table for i in key_issues if i.type == "missing_primary_key"],
        "missing_foreign_keys": [asdict(i) for i in key_issues if i.type == "missing_foreign_key"],
        "missing_indexes": [asdict(i) for i in index_issues],
        "query_issues": [asdict(i) for i in query_issues],
        "issues": [asdict(i) for i in issues],
        "issue_counts": dict(Counter(i.type for i in issues)),
        "tables": [
            {
                "name": t.name,
                "line": t.line,
                "primary_key": t.primary_key,
                "columns": [asdict(c) for c in t.columns.values()],
                "foreign_keys": [asdict(fk) for fk in t.foreign_keys],
                "unique": t.unique,
                "indexes": t.indexes,
            }
            for t in tables
        ],
        "unparsed_statements": schema.unparsed,
        "er_diagram_mermaid": generate_er_diagram(schema),
        "overall_db_score": _score(issues, len(schema.tables)),
    }
