"""Normalization checks (FR-05.2).

A schema alone does not reveal functional dependencies, so these are heuristics based
on column names and keys. Every finding says why it was raised so a reviewer can judge.
"""

import re
from collections import defaultdict

from app.analyzers.issues import Issue, Severity
from app.analyzers.naming import guess_referenced_table, referenced_entity, singular
from app.parsers.schema import Schema, Table

_NUMBERED = re.compile(r"^(?P<stem>[a-z_]+?)_?(?P<n>\d+)$")
_LIST_NAMES = {
    "tags", "phones", "emails", "skills", "courses", "subjects", "items", "categories",
    "authors", "keywords", "hobbies", "languages", "members", "students", "products",
}  # fmt: skip
_LIST_TYPES = {"VARCHAR", "CHAR", "TEXT", "TINYTEXT", "MEDIUMTEXT", "LONGTEXT", "SET", "JSON"}
# Columns that legitimately exist in many tables and say nothing about dependencies.
_GENERIC = {"id", "created_at", "updated_at", "deleted_at", "status", "notes", "description"}


def _first_nf(table: Table) -> list[Issue]:
    issues = []
    groups: dict[str, list[str]] = defaultdict(list)
    for column in table.columns.values():
        if match := _NUMBERED.match(column.key):
            groups[match["stem"]].append(column.name)
    for stem, columns in groups.items():
        if len(columns) >= 2:
            issues.append(
                Issue(
                    "repeating_group",
                    Severity.high,
                    table.name,
                    f"Columns {columns} repeat the same attribute ({stem}); this violates "
                    "1NF and limits how many values a row can hold",
                    columns=columns,
                    line=table.line,
                    suggestion=f"Move '{stem}' into its own table with a foreign key to "
                    f"{table.name}",
                )
            )
    for column in table.columns.values():
        multi = column.key in _LIST_NAMES or column.key.endswith(("_ids", "_list"))
        if multi and column.base_type in _LIST_TYPES:
            issues.append(
                Issue(
                    "multivalued_column",
                    Severity.high,
                    table.name,
                    f"'{column.name}' ({column.type}) appears to store several values in "
                    "one field (e.g. a comma-separated list), which violates 1NF",
                    columns=[column.name],
                    line=table.line,
                    suggestion="Use a separate (junction) table, one row per value",
                )
            )
    return issues


def _depends_on(schema: Schema, table: Table, key_column: str, column: str) -> bool:
    """Does `column` look like an attribute of the entity that `key_column` references?"""
    target = guess_referenced_table(schema, table, key_column)
    entity = referenced_entity(key_column)
    if entity is None and target is not None:
        entity = singular(target.name)
    if entity is None:
        return False
    if column.startswith(entity + "_") and column != key_column:
        return column != entity + "_id"  # `customer_name` describes the customer
    # `name` copied from the referenced table.
    return target is not None and column not in _GENERIC and target.column(column) is not None


def _second_nf(schema: Schema, table: Table) -> list[Issue]:
    if len(table.primary_key) < 2:
        return []
    issues = []
    for column in table.columns.values():
        if column.key in table.primary_key or column.key in _GENERIC:
            continue
        for key_column in table.primary_key:
            if _depends_on(schema, table, key_column, column.key):
                issues.append(
                    Issue(
                        "partial_dependency",
                        Severity.medium,
                        table.name,
                        f"'{column.name}' seems to depend only on '{key_column}', part of "
                        f"the composite key {table.primary_key} (violates 2NF)",
                        columns=[column.name],
                        line=table.line,
                        suggestion=f"Keep '{column.name}' only in the table that "
                        f"'{key_column}' refers to",
                    )
                )
                break
    return issues


def _third_nf(schema: Schema, table: Table) -> list[Issue]:
    issues = []
    key_columns = set(table.primary_key)
    references = [
        column.key
        for column in table.columns.values()
        if column.key not in key_columns
        and (table.fk_for(column.key) or referenced_entity(column.key))
    ]
    for column in table.columns.values():
        if column.key in key_columns or column.key in references or column.key in _GENERIC:
            continue
        for reference in references:
            if _depends_on(schema, table, reference, column.key):
                issues.append(
                    Issue(
                        "transitive_dependency",
                        Severity.medium,
                        table.name,
                        f"'{column.name}' seems to describe the row referenced by "
                        f"'{reference}', not this row (violates 3NF; the copy can drift "
                        "out of sync)",
                        columns=[column.name],
                        line=table.line,
                        suggestion=f"Remove '{column.name}' and JOIN through '{reference}'",
                    )
                )
                break
    return issues


def _bcnf(table: Table) -> list[Issue]:
    """Overlapping composite candidate keys: the textbook case of 3NF but not BCNF.

    Example: enrollments(student_id, course_id, teacher_id) with PRIMARY KEY
    (student_id, course_id) and UNIQUE (student_id, teacher_id): if each teacher
    teaches one course, teacher_id -> course_id, and teacher_id is not a key.
    A schema alone cannot prove the dependency, so this is a Low "check" issue.
    """
    keys = [k for k in [table.primary_key, *table.unique] if len(k) > 1]
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            shared = set(a) & set(b)
            if shared and set(a) != set(b):
                others = sorted((set(a) | set(b)) - shared)
                return [
                    Issue(
                        "possible_bcnf_violation",
                        Severity.low,
                        table.name,
                        f"Two overlapping composite keys ({', '.join(a)}) and ({', '.join(b)}): "
                        f"if one of {', '.join(others)} determines the other, the table is in "
                        "3NF but not BCNF",
                        columns=others,
                        line=table.line,
                        suggestion="Split the dependency into its own table "
                        f"({' , '.join(others)}) so every determinant is a key",
                    )
                ]
    return []


def analyze_normalization(schema: Schema) -> tuple[str | None, list[Issue]]:
    """Return (estimated normal form, issues). None when there are no tables."""
    if not schema.tables:
        return None, []
    first, second, third, boyce = [], [], [], []
    for table in schema.tables.values():
        first += _first_nf(table)
        second += _second_nf(schema, table)
        third += _third_nf(schema, table)
        boyce += _bcnf(table)
    level = "UNF" if first else "1NF" if second else "2NF" if third else "3NF" if boyce else "BCNF"
    return level, first + second + third + boyce
