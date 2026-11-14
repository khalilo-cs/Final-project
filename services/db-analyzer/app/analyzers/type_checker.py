"""Data types that do not fit what a column evidently stores."""

import re

from app.analyzers.issues import Issue, Severity
from app.parsers.schema import Schema

_FLOATS = {"FLOAT", "DOUBLE", "REAL", "DOUBLE PRECISION"}
_TEXTS = {"VARCHAR", "CHAR", "TEXT", "TINYTEXT", "MEDIUMTEXT", "LONGTEXT", "NVARCHAR", "NCHAR"}
_INTEGERS = {"INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "MEDIUMINT", "NUMERIC", "DECIMAL"}

_MONEY = re.compile(r"(price|amount|salary|cost|balance|fee|total|payment|wage|budget)")
_DATE = re.compile(r"(^|_)(date|dob|birthday|birth_date)$|_(at|on|date)$|^(created|updated)$")
_PHONE = re.compile(r"(phone|mobile|tel|fax|whatsapp)")
_PASSWORD = re.compile(r"^(password|passwd|pass|pwd|user_password)$")
_BOOLEAN = re.compile(r"^(is|has|can)_[a-z_]+$")


def check_types(schema: Schema) -> list[Issue]:
    issues: list[Issue] = []

    def add(table, column, kind, severity, message, suggestion=None):
        issues.append(
            Issue(kind, severity, table.name, message, [column.name], table.line, suggestion)
        )

    for table in schema.tables.values():
        for column in table.columns.values():
            name, base = column.key, column.base_type
            if _PASSWORD.match(name) and base in _TEXTS:
                if column.length is not None and column.length < 60:
                    add(
                        table,
                        column,
                        "plaintext_password",
                        Severity.high,
                        f"'{column.name}' is {column.type}: too short for a bcrypt/argon2 "
                        "hash, so passwords are probably stored in plain text",
                        "Store a hash (password_hash VARCHAR(255)) produced by bcrypt or argon2",
                    )
            elif _MONEY.search(name) and base in _FLOATS:
                add(
                    table,
                    column,
                    "float_for_money",
                    Severity.medium,
                    f"'{column.name}' uses {column.type}; floating point cannot represent "
                    "money exactly (0.1 + 0.2 != 0.3)",
                    "Use DECIMAL(12, 2)",
                )
            elif _DATE.search(name) and base in _TEXTS:
                add(
                    table,
                    column,
                    "date_as_text",
                    Severity.medium,
                    f"'{column.name}' stores a date as {column.type}; dates cannot be "
                    "compared, sorted or validated correctly",
                    "Use DATE, DATETIME or TIMESTAMP",
                )
            elif _PHONE.search(name) and base in _INTEGERS:
                add(
                    table,
                    column,
                    "phone_as_number",
                    Severity.medium,
                    f"'{column.name}' is numeric ({column.type}); leading zeros and '+' "
                    "(e.g. +967) are lost and long numbers overflow INT",
                    "Use VARCHAR(20)",
                )
            elif _BOOLEAN.match(name) and base in _TEXTS:
                add(
                    table,
                    column,
                    "boolean_as_text",
                    Severity.low,
                    f"'{column.name}' is a flag stored as {column.type}",
                    "Use BOOLEAN (TINYINT(1) in MySQL)",
                )
    return issues
