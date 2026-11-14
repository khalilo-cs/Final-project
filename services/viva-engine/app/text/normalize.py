"""Text normalization for Arabic + English matching."""

import re
import unicodedata
from dataclasses import dataclass

_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # + tatweel
_ARABIC_MAP = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
        "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    }
)  # fmt: skip
# Arabic marks are not \w, so include them or a voweled word splits into pieces.
_TOKEN = re.compile(r"[\w\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]+")


def clean_extracted(text: str) -> str:
    """NFKC turns Arabic presentation forms (common in PDF text) into normal letters."""
    return unicodedata.normalize("NFKC", text).replace("\x00", "")


def normalize(text: str) -> str:
    return _DIACRITICS.sub("", clean_extracted(text)).translate(_ARABIC_MAP).casefold()


@dataclass
class Token:
    text: str  # normalized
    start: int  # character offsets in the original text
    end: int


def tokenize(text: str) -> list[Token]:
    """Tokens of the normalized text, mapped back to offsets in `text`.

    Normalization only deletes or swaps single characters, so we normalize per token.
    """
    tokens = []
    for match in _TOKEN.finditer(text):
        value = normalize(match.group())
        if value and not value.isdigit():
            tokens.append(Token(value, match.start(), match.end()))
    return tokens
