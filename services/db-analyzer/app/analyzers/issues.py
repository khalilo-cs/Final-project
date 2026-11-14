from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    critical = "Critical"
    high = "High"
    medium = "Medium"
    low = "Low"


@dataclass
class Issue:
    type: str
    severity: Severity
    table: str
    message: str
    columns: list[str] | None = None
    line: int | None = None
    suggestion: str | None = None
