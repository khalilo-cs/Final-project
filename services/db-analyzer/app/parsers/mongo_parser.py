"""MongoDB schemas (FR-05.1) mapped onto the common Schema model.

Accepted JSON inputs (one file):

1. Sample documents per collection, e.g. from `mongoexport --jsonArray`:
       {"users": [{"_id": {"$oid": "..."}, "name": "Ali"}, ...], "orders": [...]}
2. `$jsonSchema` validators per collection (db.getCollectionInfos() / createCollection):
       {"users": {"$jsonSchema": {"properties": {"name": {"bsonType": "string"}}}}}
   or the getCollectionInfos() list itself.
3. A field -> type map per collection: {"users": {"name": "string", "age": "int"}}

Optional "indexes": {"orders": [["user_id"], ["created_at"]]} at the top level.
"""

import json
from dataclasses import dataclass, field

from app.parsers.schema import Column, ForeignKey, Schema, Table

MAX_SAMPLE = 500


class MongoSchemaError(ValueError):
    pass


@dataclass
class FieldStats:
    types: set[str] = field(default_factory=set)
    seen: int = 0
    array_of_objects: bool = False
    max_array: int = 0


def _bson_type(value) -> str:
    if isinstance(value, dict):
        if "$oid" in value:
            return "objectId"
        if "$date" in value:
            return "date"
        if "$numberDecimal" in value:
            return "decimal"
        if "$numberLong" in value or "$numberInt" in value:
            return "int"
        return "object"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return "string"


def _from_documents(name: str, docs: list) -> tuple[Table, dict[str, FieldStats], int]:
    table = Table(name=name, line=0)
    stats: dict[str, FieldStats] = {}
    docs = [d for d in docs[:MAX_SAMPLE] if isinstance(d, dict)]
    for doc in docs:
        for key, value in doc.items():
            item = stats.setdefault(key, FieldStats())
            item.seen += 1
            kind = _bson_type(value)
            if kind != "null":
                item.types.add(kind)
            if isinstance(value, list):
                item.max_array = max(item.max_array, len(value))
                item.array_of_objects |= any(isinstance(v, dict) for v in value)
    for key, item in stats.items():
        kind = "/".join(sorted(item.types)) or "null"
        table.columns[key.lower()] = Column(
            name=key, type=kind, base_type=kind.upper(), nullable=item.seen < len(docs)
        )
    return table, stats, len(docs)


def _from_json_schema(name: str, spec: dict) -> Table:
    table = Table(name=name, line=0)
    required = set(spec.get("required") or [])
    for key, prop in (spec.get("properties") or {}).items():
        kind = prop.get("bsonType") or prop.get("type") or "any"
        if isinstance(kind, list):
            kind = "/".join(str(k) for k in kind)
        table.columns[key.lower()] = Column(
            name=key, type=str(kind), base_type=str(kind).upper(), nullable=key not in required
        )
    return table


def _from_type_map(name: str, spec: dict) -> Table:
    table = Table(name=name, line=0)
    for key, kind in spec.items():
        kind = kind if isinstance(kind, str) else _bson_type(kind)
        table.columns[key.lower()] = Column(name=key, type=kind, base_type=kind.upper())
    return table


def parse_mongo(text: str) -> tuple[Schema, dict]:
    """Returns the schema plus per-collection field statistics (for sampled documents)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MongoSchemaError(f"Invalid JSON: {exc.msg} (line {exc.lineno})") from exc
    if isinstance(data, list):  # db.getCollectionInfos()
        data = {
            info["name"]: (info.get("options") or {}).get("validator") or {}
            for info in data
            if isinstance(info, dict) and "name" in info
        }
    if not isinstance(data, dict):
        raise MongoSchemaError("Expected a JSON object keyed by collection name")
    indexes = data.pop("indexes", {}) if isinstance(data.get("indexes"), dict) else {}

    schema = Schema(dialect="mongodb")
    stats: dict[str, dict] = {}
    for name, spec in data.items():
        if isinstance(spec, list):
            table, fields, count = _from_documents(name, spec)
            stats[name.lower()] = {"documents": count, "fields": fields}
        elif isinstance(spec, dict) and "$jsonSchema" in spec:
            table = _from_json_schema(name, spec["$jsonSchema"])
        elif isinstance(spec, dict):
            table = _from_type_map(name, spec)
        else:
            continue
        table.primary_key = ["_id"]
        if "_id" not in table.columns:
            table.columns["_id"] = Column(name="_id", type="objectId", base_type="OBJECTID")
        table.indexes = [[c.lower() for c in idx] for idx in indexes.get(name, []) if idx]
        schema.tables[table.key] = table

    for table in schema.tables.values():
        for column in table.columns.values():
            if column.key == "_id" or "objectid" not in column.type.lower():
                continue
            entity = column.key.removesuffix("_id").removesuffix("id").rstrip("_")
            for candidate in (entity, entity + "s", entity + "es", entity[:-1] + "ies"):
                if candidate and candidate in schema.tables and candidate != table.key:
                    table.foreign_keys.append(
                        ForeignKey([column.key], schema.tables[candidate].name, ["_id"])
                    )
                    break
    return schema, stats
