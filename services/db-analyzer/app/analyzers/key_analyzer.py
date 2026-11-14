"""Primary / foreign key problems (FR-05.3, FR-05.4)."""

from app.analyzers.issues import Issue, Severity
from app.analyzers.naming import guess_referenced_table
from app.parsers.schema import Schema


def analyze_keys(schema: Schema) -> list[Issue]:
    issues: list[Issue] = []
    for table in schema.tables.values():
        if not table.primary_key:
            issues.append(
                Issue(
                    "missing_primary_key",
                    Severity.high,
                    table.name,
                    "Table has no primary key; rows cannot be identified or referenced",
                    line=table.line,
                    suggestion=f"ALTER TABLE {table.name} ADD PRIMARY KEY (id);",
                )
            )

        for column in table.columns.values():
            if table.fk_for(column.key) or column.key == "id":
                continue
            target = guess_referenced_table(schema, table, column.name)
            if target is None:
                continue
            ref = target.primary_key[0] if len(target.primary_key) == 1 else "id"
            issues.append(
                Issue(
                    "missing_foreign_key",
                    Severity.medium,
                    table.name,
                    f"'{column.name}' looks like a reference to '{target.name}' but has no "
                    "FOREIGN KEY, so the database will accept ids that do not exist",
                    columns=[column.name],
                    line=table.line,
                    suggestion=(
                        f"ALTER TABLE {table.name} ADD FOREIGN KEY ({column.name}) "
                        f"REFERENCES {target.name}({ref});"
                    ),
                )
            )

        for fk in table.foreign_keys:
            target = schema.table(fk.ref_table)
            if target is None:
                issues.append(
                    Issue(
                        "broken_reference",
                        Severity.high,
                        table.name,
                        f"Foreign key references table '{fk.ref_table}', which is not defined",
                        columns=fk.columns,
                        line=fk.line or table.line,
                    )
                )
                continue
            ref_columns = fk.ref_columns or target.primary_key
            missing = [c for c in ref_columns if target.column(c) is None]
            if missing:
                issues.append(
                    Issue(
                        "broken_reference",
                        Severity.high,
                        table.name,
                        f"Foreign key references unknown column(s) {missing} in '{target.name}'",
                        columns=fk.columns,
                        line=fk.line or table.line,
                    )
                )
            elif ref_columns and not (
                ref_columns == target.primary_key or ref_columns in target.unique
            ):
                issues.append(
                    Issue(
                        "reference_not_unique",
                        Severity.medium,
                        table.name,
                        f"Foreign key references {target.name}({', '.join(ref_columns)}), "
                        "which is neither the primary key nor UNIQUE",
                        columns=fk.columns,
                        line=fk.line or table.line,
                    )
                )
            for column_name in fk.columns:
                column, ref = table.column(column_name), None
                if ref_columns and len(ref_columns) == len(fk.columns):
                    ref = target.column(ref_columns[fk.columns.index(column_name)])
                if column and ref and column.base_type != ref.base_type:
                    issues.append(
                        Issue(
                            "type_mismatch",
                            Severity.medium,
                            table.name,
                            f"'{column.name}' is {column.type} but references "
                            f"{target.name}.{ref.name} which is {ref.type}",
                            columns=[column.name],
                            line=fk.line or table.line,
                        )
                    )
    return issues


def analyze_indexes(schema: Schema) -> list[Issue]:
    """FK columns without an index. InnoDB (MySQL) creates these automatically."""
    if schema.dialect == "mysql":
        return []
    issues = []
    for table in schema.tables.values():
        for fk in table.foreign_keys:
            if not table.is_indexed(fk.columns):
                issues.append(
                    Issue(
                        "missing_index",
                        Severity.low,
                        table.name,
                        f"Foreign key column(s) {fk.columns} are not indexed; joins and "
                        "deletes on the parent table will scan this table",
                        columns=fk.columns,
                        line=fk.line or table.line,
                        suggestion=(
                            f"CREATE INDEX idx_{table.key}_{'_'.join(fk.columns)} "
                            f"ON {table.name} ({', '.join(fk.columns)});"
                        ),
                    )
                )
    return issues
