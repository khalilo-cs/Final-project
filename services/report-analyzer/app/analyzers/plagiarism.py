"""Compare a report against every report indexed before it (FR-06.2, FR-08.4)."""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.analyzers.fingerprint import Fingerprint, K, winnow
from app.models import Fingerprint as StoredFingerprint
from app.models import IndexedDocument
from app.text.normalize import tokenize

MIN_SOURCE_SIMILARITY = 0.02  # ignore sources sharing < 2% of the fingerprints
BOILERPLATE_MIN_CORPUS = 5
BOILERPLATE_FRACTION = 0.3  # a passage in >= 30% of reports is template text
MIN_PASSAGE_WORDS = 8
_CHUNK = 500


@dataclass
class PlagiarismResult:
    plagiarism_percentage: float
    sources: list[dict]
    passages: list[dict]
    fingerprint_count: int
    ignored_boilerplate: int
    corpus_size: int


def _matches(db: Session, document_id: str, hashes: set[int]) -> dict[int, set[str]]:
    """hash -> ids of *other* documents containing it."""
    owners: dict[int, set[str]] = defaultdict(set)
    values = list(hashes)
    for i in range(0, len(values), _CHUNK):
        rows = db.execute(
            select(StoredFingerprint.hash, StoredFingerprint.document_id).where(
                StoredFingerprint.hash.in_(values[i : i + _CHUNK]),
                StoredFingerprint.document_id != document_id,
            )
        )
        for value, owner in rows:
            owners[value].add(owner)
    return owners


def _passages(text, tokens, fingerprints, owners) -> list[dict]:
    """Merge matched k-grams into contiguous passages of the analyzed text."""
    spans: list[list[int]] = []  # [start_token, end_token_exclusive, source votes...]
    votes: list[dict[str, int]] = []
    for fingerprint in sorted(fingerprints, key=lambda f: f.position):
        sources = owners.get(fingerprint.hash)
        if not sources:
            continue
        start, end = fingerprint.position, fingerprint.position + K
        if spans and start <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
            votes.append({})
        for source in sources:
            votes[-1][source] = votes[-1].get(source, 0) + 1

    passages = []
    for (start, end), vote in zip(spans, votes, strict=True):
        if end - start < MIN_PASSAGE_WORDS:
            continue
        excerpt = text[tokens[start].start : tokens[min(end, len(tokens)) - 1].end]
        passages.append(
            {
                "text": excerpt if len(excerpt) <= 600 else excerpt[:597] + "...",
                "words": end - start,
                "source": max(vote, key=vote.get),
            }
        )
    passages.sort(key=lambda p: p["words"], reverse=True)
    return passages[:15]


def check_and_index(db: Session, document_id: str, text: str, index: bool) -> PlagiarismResult:
    tokens = tokenize(text)
    fingerprints: list[Fingerprint] = winnow(tokens)
    hashes = {f.hash for f in fingerprints}
    corpus = db.scalar(
        select(func.count()).select_from(IndexedDocument).where(IndexedDocument.id != document_id)
    )
    owners = _matches(db, document_id, hashes) if hashes else {}

    # Shared template text (university header, standard headings) is not plagiarism.
    ignored = 0
    if corpus >= BOILERPLATE_MIN_CORPUS:
        threshold = max(3, BOILERPLATE_FRACTION * corpus)
        boilerplate = {h for h, docs in owners.items() if len(docs) >= threshold}
        ignored = len(boilerplate)
        for value in boilerplate:
            del owners[value]
    considered = len(hashes) - ignored

    per_source: dict[str, int] = defaultdict(int)
    for docs in owners.values():
        for doc in docs:
            per_source[doc] += 1
    totals = dict(
        db.execute(
            select(IndexedDocument.id, IndexedDocument.fingerprint_count).where(
                IndexedDocument.id.in_(list(per_source))
            )
        ).all()
    )
    sources = []
    for doc, shared in per_source.items():
        similarity = shared / considered if considered else 0.0
        if similarity < MIN_SOURCE_SIMILARITY:
            continue
        sources.append(
            {
                "document_id": doc,
                "similarity": round(similarity, 3),  # share of THIS report found in it
                "reverse_similarity": round(shared / totals[doc], 3) if totals.get(doc) else None,
                "shared_fingerprints": shared,
            }
        )
    sources.sort(key=lambda s: s["similarity"], reverse=True)
    listed = {s["document_id"] for s in sources}
    matched = {h for h, docs in owners.items() if docs & listed}

    result = PlagiarismResult(
        plagiarism_percentage=round(100 * len(matched) / considered, 1) if considered else 0.0,
        sources=sources[:10],
        passages=_passages(text, tokens, fingerprints, {h: owners[h] & listed for h in matched}),
        fingerprint_count=len(hashes),
        ignored_boilerplate=ignored,
        corpus_size=corpus,
    )
    if index:
        _index(db, document_id, len(tokens), hashes)
    return result


def _index(db: Session, document_id: str, words: int, hashes: set[int]) -> None:
    remove_document(db, document_id, commit=False)
    db.add(IndexedDocument(id=document_id, word_count=words, fingerprint_count=len(hashes)))
    db.flush()
    rows = [{"document_id": document_id, "hash": value} for value in hashes]
    for i in range(0, len(rows), 5000):
        db.execute(insert(StoredFingerprint), rows[i : i + 5000])
    db.commit()


def remove_document(db: Session, document_id: str, commit: bool = True) -> bool:
    db.execute(delete(StoredFingerprint).where(StoredFingerprint.document_id == document_id))
    removed = db.execute(delete(IndexedDocument).where(IndexedDocument.id == document_id))
    if commit:
        db.commit()
    return bool(removed.rowcount)
