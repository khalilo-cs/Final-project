"""Fixed-size vectors for code units, compared with cosine similarity."""

from collections import Counter
from hashlib import blake2b

import numpy as np

DIM = 1024


def _slot(feature: str) -> tuple[int, float]:
    digest = blake2b(feature.encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % DIM, 1.0 if (value >> 63) & 1 else -1.0


def structural_vector(shape: list[str]) -> np.ndarray:
    """Hashed bag of 1-, 2- and 3-grams of the function's shape, sublinear tf."""
    features: Counter[str] = Counter(shape)
    features.update(" ".join(shape[i : i + 2]) for i in range(len(shape) - 1))
    features.update(" ".join(shape[i : i + 3]) for i in range(len(shape) - 2))
    vector = np.zeros(DIM, dtype=np.float32)
    for feature, count in features.items():
        slot, sign = _slot(feature)
        vector[slot] += sign * (1.0 + np.log(count))
    return normalize(vector)


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return (vector / norm).astype(np.float32) if norm else vector.astype(np.float32)


def to_bytes(vector: np.ndarray) -> bytes:
    return vector.astype(np.float16).tobytes()  # half precision: plenty for cosine


def from_bytes(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float16).astype(np.float32)
