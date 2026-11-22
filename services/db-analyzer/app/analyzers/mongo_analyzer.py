"""Design checks for MongoDB collections (document model instead of normal forms)."""

from app.analyzers.issues import Issue, Severity
from app.analyzers.naming import referenced_entity
from app.parsers.schema import Schema

LARGE_ARRAY = 100


def analyze_mongo(schema: Schema, stats: dict) -> list[Issue]:
    issues: list[Issue] = []
    names = set(schema.tables)
    for table in schema.tables.values():
        fields = (stats.get(table.key) or {}).get("fields", {})
        for column in table.columns.values():
            kinds = {k for k in column.type.split("/") if k}
            if len(kinds - {"null"}) > 1:
                issues.append(Issue(
                    "inconsistent_field_type", Severity.medium, table.name,
                    f"Field '{column.name}' holds different types ({column.type}) across documents",
                    columns=[column.name],
                    suggestion="Add a $jsonSchema validator so every document uses one type",
                ))  # fmt: skip
            entity = referenced_entity(column.name)
            if entity and column.key != "_id" and "string" in kinds:
                target = next((n for n in (entity, entity + "s") if n in names), None)
                if target:
                    issues.append(Issue(
                        "reference_as_string", Severity.low, table.name,
                        f"'{column.name}' references {target} but stores a string, not an ObjectId",
                        columns=[column.name],
                        suggestion="Store references as ObjectId so lookups and $lookup work",
                    ))  # fmt: skip
            stat = fields.get(column.name)
            if stat is not None and stat.array_of_objects and stat.max_array >= LARGE_ARRAY:
                issues.append(Issue(
                    "unbounded_array", Severity.medium, table.name,
                    f"'{column.name}' embeds {stat.max_array}+ sub-documents; arrays that keep "
                    "growing hit the 16 MB document limit",
                    columns=[column.name],
                    suggestion="Move the items to their own collection with a reference",
                ))  # fmt: skip
        for fk in table.foreign_keys:
            if not table.is_indexed(fk.columns) and table.indexes is not None:
                issues.append(Issue(
                    "missing_index", Severity.low, table.name,
                    f"Reference '{fk.columns[0]}' to {fk.ref_table} has no index",
                    columns=fk.columns,
                    suggestion=f"db.{table.name}.createIndex({{{fk.columns[0]}: 1}})",
                ))  # fmt: skip
        if not fields and len(table.columns) <= 1:
            issues.append(Issue(
                "empty_collection", Severity.low, table.name,
                "No fields could be read for this collection",
            ))  # fmt: skip
    return issues
