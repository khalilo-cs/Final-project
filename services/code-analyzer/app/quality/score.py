"""Heuristic 0-100 scores. Version 0: simple, explainable penalties.

The weights are starting points to be tuned against faculty grades (plan phase 8).
"""

from app.security.models import Severity

_SEVERITY_PENALTY = {
    Severity.critical: 25,
    Severity.high: 15,
    Severity.medium: 7,
    Severity.low: 2,
}


def security_score(severity_counts: dict[Severity, int]) -> float:
    penalty = sum(_SEVERITY_PENALTY[sev] * count for sev, count in severity_counts.items())
    return float(max(0, 100 - penalty))


def quality_score(
    avg_cyclomatic: float, smell_count: int, code_lines: int, files: int, unparsable: int
) -> float:
    if files == 0:
        return 0.0
    complexity_penalty = min(30.0, max(0.0, avg_cyclomatic - 5) * 4)
    smells_per_kloc = smell_count / max(code_lines, 1) * 1000
    smell_penalty = min(40.0, smells_per_kloc * 2)
    parse_penalty = min(30.0, unparsable / files * 100)
    return round(max(0.0, 100 - complexity_penalty - smell_penalty - parse_penalty), 1)
