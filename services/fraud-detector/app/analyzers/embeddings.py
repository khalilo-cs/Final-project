"""Optional code embeddings from an OpenAI-compatible /v1/embeddings server."""

import httpx
import numpy as np

from app.analyzers.vectors import normalize
from app.config import get_settings

BATCH = 32
MAX_CHARS = 4000  # code models read ~512-8k tokens; the start of a function matters most
# Tests replace this with httpx.MockTransport.
transport: httpx.BaseTransport | None = None


class EmbeddingError(Exception):
    pass


def enabled() -> bool:
    return bool(get_settings().embedding_url)


def embed(texts: list[str]) -> list[np.ndarray]:
    s = get_settings()
    headers = {"Authorization": f"Bearer {s.embedding_api_key}"} if s.embedding_api_key else {}
    vectors: list[np.ndarray] = []
    try:
        with httpx.Client(base_url=s.embedding_url or "", timeout=s.embedding_timeout_seconds,
                          transport=transport) as client:  # fmt: skip
            for i in range(0, len(texts), BATCH):
                batch = [t[:MAX_CHARS] for t in texts[i : i + BATCH]]
                response = client.post(
                    "/v1/embeddings", json={"model": s.embedding_model, "input": batch},
                    headers=headers,
                )  # fmt: skip
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda d: d["index"])
                if len(data) != len(batch):
                    raise EmbeddingError("server returned a different number of vectors")
                vectors.extend(
                    normalize(np.asarray(d["embedding"], dtype=np.float32)) for d in data
                )
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise EmbeddingError(f"{type(exc).__name__}: {exc}") from exc
    return vectors
