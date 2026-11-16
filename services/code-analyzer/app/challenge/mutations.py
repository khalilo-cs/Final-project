"""Comprehension fingerprint: one small defect seeded into the student's own function.

The author of a function knows its logic and notices that `<` became `<=`; someone
who bought or copied the project has to read it for the first time. The original is
known, so finding and fixing the defect is checked automatically.

Mutations are chosen on the text of the function with strings and comments masked,
so they work for every language the analyzers read.
"""

import random
import re
from dataclasses import dataclass
from pathlib import Path

from app.analyzers.base_analyzer import FileAnalysis, FunctionInfo

MIN_LINES = 6
MAX_LINES = 60
_MASK = re.compile(
    r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`'
    r"|//[^\n]*|/\*[\s\S]*?\*/|#[^\n]*"
)


@dataclass(frozen=True)
class Operator:
    kind: str
    pattern: re.Pattern
    replacement: str
    description_ar: str
    description: str


def _op(kind: str, pattern: str, replacement: str, ar: str, en: str) -> Operator:
    return Operator(kind, re.compile(pattern), replacement, ar, en)


# Each pattern has one group: the text that is replaced. Spaces around operators keep
# generics (List<Loan>), arrows (->, =>) and shifts out.
OPERATORS = [
    _op("boundary", r"(?<=\s)(<=)(?=\s)", "<", "حدّ المقارنة: <= صارت <", "<= became <"),
    _op("boundary", r"(?<=\s)(>=)(?=\s)", ">", "حدّ المقارنة: >= صارت >", ">= became >"),
    _op("boundary", r"(?<=\s)(<)(?=\s)", "<=", "حدّ المقارنة: < صارت <=", "< became <="),
    _op("boundary", r"(?<=\s)(>)(?=\s)", ">=", "حدّ المقارنة: > صارت >=", "> became >="),
    _op("equality", r"(?<=\s)(===?)(?=\s)", "!=", "المساواة صارت عدم مساواة", "== became !="),
    _op("equality", r"(?<=\s)(!==?)(?=\s)", "==", "عدم المساواة صارت مساواة", "!= became =="),
    _op("logic", r"(?<=\s)(&&)(?=\s)", "||", "«و» المنطقية صارت «أو»", "&& became ||"),
    _op("logic", r"(?<=\s)(\|\|)(?=\s)", "&&", "«أو» المنطقية صارت «و»", "|| became &&"),
    _op("logic", r"(?<=\s)(and)(?=\s)", "or", "«and» صارت «or»", "and became or"),
    _op("logic", r"(?<=\s)(or)(?=\s)", "and", "«or» صارت «and»", "or became and"),
    _op("arithmetic", r"(?<=[\w)\]]\s)(\+)(?=\s[\w(])", "-", "الجمع صار طرحاً", "+ became -"),
    _op("arithmetic", r"(?<=[\w)\]]\s)(-)(?=\s[\w(])", "+", "الطرح صار جمعاً", "- became +"),
    _op("arithmetic", r"(?<=\s)(\+=)(?=\s)", "-=", "+= صارت -=", "+= became -="),
    _op("arithmetic", r"(?<=\s)(-=)(?=\s)", "+=", "-= صارت +=", "-= became +="),
    _op("constant", r"(?<=[<>=]\s)(0)(?=\s*[);:\]]|\s*$)", "1", "الثابت 0 صار 1", "0 became 1"),
    _op("constant", r"(?<=[<>=]\s)(1)(?=\s*[);:\]]|\s*$)", "0", "الثابت 1 صار 0", "1 became 0"),
    _op("boolean", r"(?<=return\s)(true)\b", "false", "القيمة المرجعة انعكست", "return flipped"),
    _op("boolean", r"(?<=return\s)(false)\b", "true", "القيمة المرجعة انعكست", "return flipped"),
    _op("boolean", r"(?<=return\s)(True)\b", "False", "القيمة المرجعة انعكست", "return flipped"),
    _op("boolean", r"(?<=return\s)(False)\b", "True", "القيمة المرجعة انعكست", "return flipped"),
]


_PRIORITY = {"logic": 0, "equality": 0, "arithmetic": 0, "boolean": 1, "constant": 2, "boundary": 3}


def mask(text: str) -> str:
    """Strings and comments replaced by spaces of the same length (newlines kept)."""
    return _MASK.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)


@dataclass
class Mutation:
    line: int  # 1-based, within the file
    original_line: str
    mutated_line: str
    kind: str
    description_ar: str
    description: str


def candidates(lines: list[str], first_line: int, body_from: int) -> list[Mutation]:
    """Every single-token change possible in the function (`body_from`: skip the header)."""
    masked = mask("\n".join(lines)).split("\n")
    found = []
    for offset, (line, clean) in enumerate(zip(lines, masked, strict=True)):
        if offset < body_from or "+" in clean and clean != line and '"' in line:
            continue  # header, or string concatenation (a - there would not compile)
        for operator in OPERATORS:
            for match in operator.pattern.finditer(clean):
                start, end = match.span(1)
                mutated = line[:start] + operator.replacement + line[end:]
                found.append(Mutation(first_line + offset, line, mutated, operator.kind,
                                      operator.description_ar, operator.description))  # fmt: skip
    return found


def normalize(line: str) -> str:
    return re.sub(r"\s+", "", line)


@dataclass
class Challenge:
    file: str
    function: str
    language: str
    start_line: int
    code: str  # the function with the defect, as shown to the student
    mutation: Mutation


def _eligible(file: FileAnalysis) -> list[FunctionInfo]:
    return [f for f in file.functions if MIN_LINES <= f.length <= MAX_LINES]


def make_challenges(
    root: Path, files: list[FileAnalysis], count: int, rng: random.Random
) -> list[Challenge]:
    """Up to `count` challenges, each in a different function, hardest functions first."""
    pool = []
    for file in files:
        if file.parse_error or "test" in file.path.lower():
            continue
        for function in _eligible(file):
            pool.append((file, function))
    # The most complex functions are the ones only the author can explain; shuffle within
    # equal complexity so two students with similar code do not get the same challenge.
    rng.shuffle(pool)
    pool.sort(key=lambda item: item[1].cyclomatic_complexity, reverse=True)

    challenges: list[Challenge] = []
    kinds_used: set[str] = set()
    for file, function in pool:
        if len(challenges) >= count:
            break
        try:
            source = (root / file.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_lines = source.splitlines()
        lines = all_lines[function.line - 1 : function.end_line]
        options = candidates(lines, function.line, body_from=1)
        if not options:
            continue
        # Prefer a kind of defect not used yet in this session, and among those the kinds
        # that almost always change behaviour (a boundary change can be equivalent).
        fresh = [m for m in options if m.kind not in kinds_used] or options
        best = min(_PRIORITY.get(m.kind, 9) for m in fresh)
        mutation = rng.choice([m for m in fresh if _PRIORITY.get(m.kind, 9) == best])
        kinds_used.add(mutation.kind)
        shown = list(lines)
        shown[mutation.line - function.line] = mutation.mutated_line
        challenges.append(Challenge(file.path, function.qualified_name, file.language,
                                    function.line, "\n".join(shown), mutation))  # fmt: skip
    return challenges
