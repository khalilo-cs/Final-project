"""Winnowing (Schleimer, Wilkerson & Aiken 2003), the algorithm behind MOSS.

Hash every k-gram of words, then keep the minimum hash in each window of w
consecutive k-grams. Any shared passage of at least w + k - 1 words is guaranteed
to produce a shared fingerprint, while the index stays small.
"""

from dataclasses import dataclass
from hashlib import blake2b

from app.text.normalize import Token

K = 5  # words per k-gram
W = 4  # window size -> passages of >= 8 words always match


@dataclass(frozen=True)
class Fingerprint:
    hash: int
    position: int  # index of the first token of the k-gram


def _hash(words: list[str]) -> int:
    digest = blake2b(" ".join(words).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)  # fits a signed BIGINT


def winnow(tokens: list[Token], k: int = K, w: int = W) -> list[Fingerprint]:
    words = [token.text for token in tokens]
    hashes = [_hash(words[i : i + k]) for i in range(len(words) - k + 1)]
    if not hashes:
        return []
    if len(hashes) <= w:
        best = min(range(len(hashes)), key=lambda i: (hashes[i], -i))
        return [Fingerprint(hashes[best], best)]

    selected: list[Fingerprint] = []
    previous = -1
    for start in range(len(hashes) - w + 1):
        window = range(start, start + w)
        # Rightmost minimum, as in the paper, so runs of equal hashes select once.
        best = min(window, key=lambda i: (hashes[i], -i))
        if best != previous:
            selected.append(Fingerprint(hashes[best], best))
            previous = best
    return selected
