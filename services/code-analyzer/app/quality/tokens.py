"""Language-agnostic code tokens, normalized so that renaming hides nothing.

Every identifier that is not a keyword becomes `V`, every string `S`, every number
`N`; comments and whitespace disappear. Two files that differ only in names,
comments, literals or formatting produce the same token stream.
"""

import re
from dataclasses import dataclass
from hashlib import blake2b

SOURCE_EXTENSIONS = {
    ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".php", ".cs", ".cpp", ".cc", ".c", ".h",
    ".hpp", ".kt", ".dart", ".go", ".rb", ".swift",
}  # fmt: skip
# Generated, vendored or framework scaffolding: shared by everyone, says nothing.
IGNORED_PATH_PARTS = {
    "node_modules", "vendor", "dist", "build", "target", "migrations", ".git", "venv",
    ".venv", "__pycache__", "bin", "obj", ".idea", ".vscode",
}  # fmt: skip

KEYWORDS = {
    # control flow / structure shared by most languages
    "if", "else", "elif", "for", "while", "do", "switch", "case", "default", "break",
    "continue", "return", "try", "catch", "except", "finally", "throw", "throws", "raise",
    "class", "interface", "enum", "struct", "def", "function", "fun", "func", "lambda",
    "new", "delete", "this", "self", "super", "null", "None", "nil", "true", "false",
    "True", "False", "import", "from", "package", "namespace", "using", "include",
    "public", "private", "protected", "static", "final", "const", "let", "var", "val",
    "void", "int", "long", "float", "double", "char", "bool", "boolean", "string", "String",
    "async", "await", "yield", "in", "is", "not", "and", "or", "with", "as", "pass",
    "extends", "implements", "abstract", "override", "virtual", "echo", "print",
}  # fmt: skip

_TOKEN = re.compile(
    r'(?P<ws>\s+)'
    r'|(?P<comment>//[^\n]*|/\*.*?\*/|#[^\n]*)'
    r'|(?P<str>"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`)'
    r'|(?P<num>\d[\w.]*)'
    r'|(?P<id>[A-Za-z_$][\w$]*)'
    r'|(?P<op>\S)',
    re.DOTALL,
)  # fmt: skip


@dataclass(frozen=True)
class Token:
    value: str
    line: int


def tokenize(source: str) -> list[Token]:
    tokens = []
    line = 1
    for match in _TOKEN.finditer(source):
        kind, text = match.lastgroup, match.group()
        if kind == "str":
            tokens.append(Token("S", line))
        elif kind == "num":
            tokens.append(Token("N", line))
        elif kind == "id":
            tokens.append(Token(text if text in KEYWORDS else "V", line))
        elif kind == "op":
            tokens.append(Token(text, line))
        line += text.count("\n")
    return tokens


K = 15  # tokens per k-gram
W = 8  # winnowing window: any shared run of >= K + W - 1 = 22 tokens is found


@dataclass(frozen=True)
class Fingerprint:
    hash: int
    line: int


def _hash(values: list[str]) -> int:
    return int.from_bytes(blake2b(" ".join(values).encode(), digest_size=8).digest(), "big",
                          signed=True)  # fmt: skip


def fingerprints(tokens: list[Token], k: int = K, w: int = W) -> list[Fingerprint]:
    values = [t.value for t in tokens]
    hashes = [_hash(values[i : i + k]) for i in range(len(values) - k + 1)]
    if not hashes:
        return []
    selected, previous = [], -1
    for start in range(max(1, len(hashes) - w + 1)):
        window = range(start, min(start + w, len(hashes)))
        best = min(window, key=lambda i: (hashes[i], -i))
        if best != previous:
            selected.append(Fingerprint(hashes[best], tokens[best].line))
            previous = best
    return selected
