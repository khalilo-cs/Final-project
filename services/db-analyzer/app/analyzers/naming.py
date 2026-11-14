"""Name heuristics shared by the key and normalization checks."""

import re

_ID_SUFFIX = re.compile(r"^(?P<entity>[a-z][a-z0-9_]*?)_?id$")
_CAMEL_ID = re.compile(r"^(?P<entity>[a-z][a-zA-Z0-9]*?)Id$")


def referenced_entity(column: str) -> str | None:
    """`user_id` / `userId` / `userid` -> `user`. Plain `id` -> None."""
    if match := _CAMEL_ID.match(column):
        return match["entity"].lower()
    lowered = column.lower()
    if lowered == "id" or not lowered.endswith("id"):
        return None
    if match := _ID_SUFFIX.match(lowered):
        entity = match["entity"].rstrip("_")
        return entity or None
    return None


def table_candidates(entity: str) -> list[str]:
    """Table names an entity could be stored in: user -> users, tbl_users, categories..."""
    plurals = [entity, entity + "s", entity + "es"]
    if entity.endswith("y"):
        plurals.append(entity[:-1] + "ies")
    return [prefix + name for prefix in ("", "tbl_", "tb_") for name in plurals]


def guess_referenced_table(schema, table, column: str):
    """The table a column like `user_id` points to, using its FK or else its name."""
    fk = table.fk_for(column)
    if fk is not None:
        return schema.table(fk.ref_table)
    entity = referenced_entity(column)
    if entity is None:
        return None
    for candidate in table_candidates(entity):
        target = schema.table(candidate)
        if target is not None and target is not table:
            return target
    return None


def singular(table: str) -> str:
    name = table.lower().removeprefix("tbl_").removeprefix("tb_")
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith(("ses", "xes", "ches", "shes")):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name
