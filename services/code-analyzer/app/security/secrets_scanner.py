"""Hardcoded secrets: known token formats + suspicious assignments (any language)."""

import math
import re

from app.security.models import Severity, Vulnerability

_KNOWN_FORMATS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
]

_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(?P<name>[\w.\-]*(?:password|passwd|pwd|secret|api[_-]?key|token|access[_-]?key|auth)[\w\-]*)
    ["']?\s*[:=]\s*
    (?P<quote>["'])(?P<value>[^"'\n]{4,})(?P=quote)
    """
)
_PLACEHOLDER = re.compile(
    r"(?i)^(?:change[-_ ]?me|your[-_ ].*|x{3,}|\*{3,}|<.*>|\{.*\}|\$\{?.*|%\(?.*|"
    r"example.*|placeholder|todo|none|null|test|password|secret|token)$"
)


def shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = {char: text.count(char) for char in set(text)}
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def _mask(value: str) -> str:
    return value[:2] + "*" * 6 if len(value) > 4 else "*" * 6


def scan_secrets(path: str, source: str) -> list[Vulnerability]:
    findings: list[Vulnerability] = []
    for number, line in enumerate(source.splitlines(), 1):
        if len(line) > 2000:  # minified / generated content
            continue
        for label, pattern in _KNOWN_FORMATS:
            if pattern.search(line):
                findings.append(
                    Vulnerability(
                        "Hardcoded Secret",
                        Severity.critical,
                        path,
                        number,
                        f"{label} committed to the source code",
                    )
                )
                break
        else:
            match = _ASSIGNMENT.search(line)
            if not match:
                continue
            value = match["value"]
            if _PLACEHOLDER.match(value) or " " in value.strip():
                continue
            # Short, low-entropy literals are usually labels or field names.
            if len(value) < 8 and shannon_entropy(value) < 2.5:
                continue
            findings.append(
                Vulnerability(
                    "Hardcoded Secret",
                    Severity.high,
                    path,
                    number,
                    f"Hardcoded credential assigned to '{match['name']}'",
                    evidence=f"{match['name']} = {_mask(value)}",
                )
            )
    return findings
