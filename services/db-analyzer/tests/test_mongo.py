import json

from app.services.database_analyzer import analyze_database
from tests.test_api import post

SAMPLES = {
    "users": [
        {"_id": {"$oid": "1"}, "name": "Ali", "age": 20},
        {"_id": {"$oid": "2"}, "name": "Sara", "age": "21"},
    ],
    "orders": [
        {"_id": {"$oid": "9"}, "user_id": {"$oid": "1"}, "items": [{"sku": i} for i in range(120)]},
        {"_id": {"$oid": "8"}, "customerId": "2", "items": []},
    ],
    "customers": [{"_id": {"$oid": "2"}, "name": "X"}],
    "indexes": {"orders": [["customerId"]]},
}


def test_mongo_sample_documents():
    result = analyze_database(json.dumps(SAMPLES), "mongodb")
    assert result["dialect"] == "mongodb"
    assert result["total_tables"] == 3
    assert result["normalization_level"] == "document model"
    types = {(i["type"], i["table"]) for i in result["issues"]}
    assert ("inconsistent_field_type", "users") in types
    assert ("unbounded_array", "orders") in types
    assert ("reference_as_string", "orders") in types
    assert ("missing_index", "orders") in types  # user_id reference has no index
    orders = next(t for t in result["tables"] if t["name"] == "orders")
    assert orders["foreign_keys"][0]["ref_table"] == "users"
    assert "orders }o--" in result["er_diagram_mermaid"] or "users" in result["er_diagram_mermaid"]


def test_mongo_json_schema_validator():
    spec = {
        "students": {
            "$jsonSchema": {
                "required": ["name"],
                "properties": {"name": {"bsonType": "string"}, "gpa": {"bsonType": "double"}},
            }
        }
    }
    result = analyze_database(json.dumps(spec), "mongodb")
    columns = {c["name"]: c for c in result["tables"][0]["columns"]}
    assert columns["name"]["nullable"] is False and columns["gpa"]["type"] == "double"


def test_mongo_bad_json_is_a_400():
    response = post(b"{not json", dialect="mongodb")
    assert response.status_code == 400
    assert "Invalid JSON" in response.json()["detail"]
