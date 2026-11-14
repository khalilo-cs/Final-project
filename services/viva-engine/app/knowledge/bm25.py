"""BM25 search, implemented here so the system needs no external embedding model."""

import math
from collections import Counter

from app.text.normalize import tokenize

K1, B = 1.5, 0.75


def terms(text: str) -> list[str]:
    return [token.text for token in tokenize(text) if len(token.text) > 1]


class BM25Index:
    def __init__(self, documents: list[tuple[str, str]]) -> None:
        """documents: [(id, text), ...]"""
        self.ids = [doc_id for doc_id, _ in documents]
        self.frequencies = [Counter(terms(text)) for _, text in documents]
        self.lengths = [sum(freq.values()) for freq in self.frequencies]
        self.average = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        document_frequency: Counter[str] = Counter()
        for freq in self.frequencies:
            document_frequency.update(freq.keys())
        n = len(documents)
        self.idf = {
            term: math.log(1 + (n - df + 0.5) / (df + 0.5))
            for term, df in document_frequency.items()
        }

    def search(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        query_terms = set(terms(query))
        scored = []
        for index, freq in enumerate(self.frequencies):
            score = 0.0
            for term in query_terms:
                if term not in freq:
                    continue
                tf = freq[term]
                norm = 1 - B + B * self.lengths[index] / (self.average or 1)
                score += self.idf[term] * tf * (K1 + 1) / (tf + K1 * norm)
            if score > 0:
                scored.append((self.ids[index], score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]


def jaccard(a: str, b: str) -> float:
    left, right = set(terms(a)), set(terms(b))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
