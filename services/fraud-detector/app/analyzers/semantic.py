"""Find functions that were copied and then rewritten (renamed, restructured, translated).

Each substantial function becomes a vector (its structure, and optionally a code-model
embedding) and is compared with every function of the projects indexed before it.
Patterns most projects share (CRUD handlers, login forms) are ignored automatically.
"""

from collections import defaultdict
from pathlib import Path

import numpy as np
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.analyzers import embeddings
from app.analyzers.units import Unit, project_units
from app.analyzers.vectors import from_bytes, structural_vector, to_bytes
from app.config import get_settings
from app.models import CodeDocument, CodeUnit

BOILERPLATE_MIN_CORPUS = 5
BOILERPLATE_FRACTION = 0.3
MIN_SOURCE_SIMILARITY = 0.05
_LOAD_BATCH = 5000


def _matches(db: Session, kind: str, mine: np.ndarray, others: set[str], threshold: float):
    """{my unit index: {doc: (similarity, other unit row)}} for pairs above threshold."""
    found: dict[int, dict[str, tuple[float, tuple]]] = defaultdict(dict)
    if not len(mine):
        return found
    query = (
        select(CodeUnit.document_id, CodeUnit.file, CodeUnit.name, CodeUnit.start_line,
               CodeUnit.end_line, CodeUnit.vector)
        .where(CodeUnit.kind == kind, CodeUnit.document_id.not_in(others))
        .execution_options(yield_per=_LOAD_BATCH)
    )  # fmt: skip
    for batch in db.execute(query).partitions():
        matrix = np.stack([from_bytes(row.vector) for row in batch])
        if matrix.shape[1] != mine.shape[1]:
            continue  # vectors from another embedding model: not comparable
        scores = mine @ matrix.T
        for i, j in zip(*np.nonzero(scores >= threshold), strict=True):
            row, score = batch[j], float(scores[i, j])
            best = found[i].get(row.document_id)
            if best is None or score > best[0]:
                found[i][row.document_id] = (score, tuple(row[:5]))
    return found


def _covered(unit: Unit, lines_by_file: dict) -> float:
    """Share of the function's lines that token fingerprints already matched."""
    covered = set()
    for start, end in lines_by_file.get(unit.file, []):
        covered.update(range(max(start, unit.start_line), min(end, unit.end_line) + 1))
    return len(covered) / unit.lines


def compare_and_index(
    db: Session, document_id: str, root: Path, exclude: set[str], token_lines: dict,
    index: bool = True,
) -> dict:  # fmt: skip
    """`token_lines`: {doc: {my_file: [(start, end), ...]}}, the lines token fingerprints
    already matched. A function they cover less than half of is reported as rewritten."""
    s = get_settings()
    units = project_units(root, s.semantic_min_shape)
    others = exclude | {document_id}
    corpus = db.scalar(
        select(func.count()).select_from(CodeDocument).where(CodeDocument.id.not_in(others))
    )
    vectors = {"structural": np.stack([structural_vector(u.shape) for u in units])
               if units else np.zeros((0, 1), np.float32)}  # fmt: skip
    thresholds = {"structural": s.structural_threshold}
    embedding_error = None
    if embeddings.enabled() and units:
        try:
            vectors["embedding"] = np.stack(embeddings.embed([u.source for u in units]))
            thresholds["embedding"] = s.embedding_threshold
        except embeddings.EmbeddingError as exc:
            embedding_error = str(exc)

    # unit index -> doc -> (similarity, other unit, methods)
    merged: dict[int, dict[str, tuple[float, tuple, set[str]]]] = defaultdict(dict)
    for kind, mine in vectors.items():
        for i, per_doc in _matches(db, kind, mine, others, thresholds[kind]).items():
            for doc, (score, other) in per_doc.items():
                previous = merged[i].get(doc)
                methods = (previous[2] if previous else set()) | {kind}
                if previous is None or score > previous[0]:
                    merged[i][doc] = (score, other, methods)
                else:
                    merged[i][doc] = (previous[0], previous[1], methods)

    ignored = 0
    if corpus >= BOILERPLATE_MIN_CORPUS:
        limit = max(3, BOILERPLATE_FRACTION * corpus)
        for i in [i for i, docs in merged.items() if len(docs) >= limit]:
            del merged[i]
            ignored += 1

    total_lines = sum(u.lines for u in units) or 1
    per_doc: dict[str, list[dict]] = defaultdict(list)
    for i, docs in merged.items():
        unit: Unit = units[i]
        for doc, (score, other, methods) in docs.items():
            _, other_file, other_name, other_start, other_end = other
            per_doc[doc].append({
                "file": unit.file, "name": unit.name, "lines": [unit.start_line, unit.end_line],
                "other_file": other_file, "other_name": other_name,
                "other_lines": [other_start, other_end], "similarity": round(score, 3),
                "methods": sorted(methods),
                "token_coverage": round(coverage := _covered(unit, token_lines.get(doc, {})), 2),
                "rewritten": coverage < 0.5,
                "_size": unit.lines,
            })  # fmt: skip
    sources = []
    for doc, matches in per_doc.items():
        similarity = sum(m.pop("_size") for m in matches) / total_lines
        if similarity < MIN_SOURCE_SIMILARITY:
            continue
        matches.sort(key=lambda m: m["similarity"], reverse=True)
        sources.append({
            "document_id": doc, "similarity": round(min(similarity, 1.0), 3),
            "matched_functions": len(matches),
            "rewritten_functions": sum(m["rewritten"] for m in matches),
            "functions": matches[:10],
        })  # fmt: skip
    sources.sort(key=lambda src: src["similarity"], reverse=True)
    if index:
        _index(db, document_id, units, vectors)
    return {
        "max_similarity": sources[0]["similarity"] if sources else 0.0,
        "sources": sources[:10],
        "functions_compared": len(units),
        "ignored_common_patterns": ignored,
        "methods": sorted(vectors),
        "embedding_error": embedding_error,
    }


def _index(db: Session, document_id: str, units: list[Unit], vectors: dict) -> None:
    db.execute(delete(CodeUnit).where(CodeUnit.document_id == document_id))
    rows = [
        {"document_id": document_id, "kind": kind, "file": u.file[:500], "name": u.name,
         "start_line": u.start_line, "end_line": u.end_line, "vector": to_bytes(vectors[kind][i])}
        for kind in vectors for i, u in enumerate(units)
    ]  # fmt: skip
    for i in range(0, len(rows), 2000):
        db.execute(insert(CodeUnit), rows[i : i + 2000])
    db.commit()
