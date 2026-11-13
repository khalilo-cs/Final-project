from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    critical = "Critical"
    high = "High"
    medium = "Medium"
    low = "Low"


@dataclass
class Vulnerability:
    type: str
    severity: Severity
    file: str
    line: int
    description: str
    evidence: str = ""
