"""ER diagram in Mermaid `erDiagram` syntax (FR-05.6)."""

import re

from app.parsers.schema import Schema

_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _ident(name: str) -> str:
    cleaned = _SAFE.sub("_", name) or "_"
    return cleaned if not cleaned[0].isdigit() else "_" + cleaned


def generate_er_diagram(schema: Schema) -> str:
    lines = ["erDiagram"]
    for table in schema.tables.values():
        lines.append(f"    {_ident(table.name)} {{")
        for column in table.columns.values():
            keys = []
            if column.key in table.primary_key:
                keys.append("PK")
            if table.fk_for(column.key):
                keys.append("FK")
            if [column.key] in table.unique:
                keys.append("UK")
            marker = f" {','.join(keys)}" if keys else ""
            type_name = _ident(column.base_type.lower().replace(" ", "_"))
            lines.append(f"        {type_name} {_ident(column.name)}{marker}")
        lines.append("    }")

    for table in schema.tables.values():
        for fk in table.foreign_keys:
            target = schema.table(fk.ref_table)
            if target is None:
                continue
            # Child side: "one or many" unless the FK is itself unique (1:1).
            unique = fk.columns == table.primary_key or fk.columns in table.unique
            nullable = any(
                (column := table.column(name)) is not None and column.nullable
                for name in fk.columns
            )
            parent = "|o" if nullable else "||"
            child = "o|" if unique else "o{"
            label = _ident(fk.name or "_".join(fk.columns))
            lines.append(
                f"    {_ident(target.name)} {parent}--{child} {_ident(table.name)} : {label}"
            )
    return "\n".join(lines) + "\n"
