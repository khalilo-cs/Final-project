"""Compare a project's code with every project indexed before it."""

from collections import defaultdict
from pathlib import Path

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.analyzers.tokens import IGNORED_PATH_PARTS, SOURCE_EXTENSIONS, fingerprints, tokenize
from app.models import CodeDocument, CodeFingerprint, CodeUnit

MIN_FILE_TOKENS = 40
MAX_FILE_BYTES = 500_000
MIN_SOURCE_SIMILARITY = 0.05
BOILERPLATE_MIN_CORPUS = 5
BOILERPLATE_FRACTION = 0.3
_CHUNK = 500


def project_fingerprints(root: Path) -> dict[int, tuple[str, int]]:
    """hash -> (file, line) of its first occurrence, over all source files."""
    found: dict[int, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if set(relative.parts[:-1]) & IGNORED_PATH_PARTS or ".min." in path.name:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        tokens = tokenize(path.read_text(encoding="utf-8", errors="replace"))
        if len(tokens) < MIN_FILE_TOKENS:
            continue
        for fingerprint in fingerprints(tokens):
            found.setdefault(fingerprint.hash, (relative.as_posix(), fingerprint.line))
    return found


def compare_and_index(
    db: Session, document_id: str, root: Path, exclude: set[str], index: bool = True
) -> dict:
    mine = project_fingerprints(root)
    others = exclude | {document_id}
    corpus = db.scalar(
        select(func.count()).select_from(CodeDocument).where(CodeDocument.id.not_in(others))
    )
    owners: dict[int, list[tuple[str, str, int]]] = defaultdict(list)  # hash -> (doc, file, line)
    values = list(mine)
    for i in range(0, len(values), _CHUNK):
        rows = db.execute(
            select(
                CodeFingerprint.hash,
                CodeFingerprint.document_id,
                CodeFingerprint.file,
                CodeFingerprint.line,
            ).where(
                CodeFingerprint.hash.in_(values[i : i + _CHUNK]),
                CodeFingerprint.document_id.not_in(others),
            )
        )
        for value, doc, file, line in rows:
            owners[value].append((doc, file, line))

    ignored = 0
    if corpus >= BOILERPLATE_MIN_CORPUS:
        threshold = max(3, BOILERPLATE_FRACTION * corpus)
        for value in [h for h, o in owners.items() if len({d for d, _, _ in o}) >= threshold]:
            del owners[value]
            ignored += 1
    considered = max(len(mine) - ignored, 0)

    per_doc: dict[str, dict] = defaultdict(lambda: {"shared": 0, "pairs": defaultdict(list)})
    for value, places in owners.items():
        my_file, my_line = mine[value]
        for doc, file, line in places:
            per_doc[doc]["shared"] += 1
            per_doc[doc]["pairs"][(my_file, file)].append((my_line, line))
    totals = dict(
        db.execute(
            select(CodeDocument.id, CodeDocument.fingerprint_count).where(
                CodeDocument.id.in_(list(per_doc))
            )
        ).all()
    )
    sources = []
    for doc, data in per_doc.items():
        similarity = data["shared"] / considered if considered else 0.0
        if similarity < MIN_SOURCE_SIMILARITY:
            continue
        pairs = sorted(data["pairs"].items(), key=lambda kv: len(kv[1]), reverse=True)[:5]
        sources.append(
            {
                "document_id": doc,
                "similarity": round(similarity, 3),
                "reverse_similarity": round(data["shared"] / totals[doc], 3)
                if totals.get(doc)
                else None,
                "matched_files": [
                    {
                        "file": mine_file,
                        "lines": [min(m for m, _ in hits), max(m for m, _ in hits)],
                        "other_file": other_file,
                        "other_lines": [min(o for _, o in hits), max(o for _, o in hits)],
                        "fingerprints": len(hits),
                    }
                    for (mine_file, other_file), hits in pairs
                ],
            }
        )
    sources.sort(key=lambda s: s["similarity"], reverse=True)
    if index:
        _index(db, document_id, mine)
    return {
        "max_similarity": sources[0]["similarity"] if sources else 0.0,
        "sources": sources[:10],
        "fingerprint_count": len(mine),
        "ignored_boilerplate": ignored,
        "corpus_size": corpus,
    }


def _index(db: Session, document_id: str, mine: dict[int, tuple[str, int]]) -> None:
    remove_document(db, document_id, commit=False)
    files = len({file for file, _ in mine.values()})
    db.add(CodeDocument(id=document_id, files=files, fingerprint_count=len(mine)))
    db.flush()
    rows = [{"document_id": document_id, "hash": h, "file": f, "line": line}
            for h, (f, line) in mine.items()]  # fmt: skip
    for i in range(0, len(rows), 5000):
        db.execute(insert(CodeFingerprint), rows[i : i + 5000])
    db.commit()


def remove_document(db: Session, document_id: str, commit: bool = True) -> None:
    db.execute(delete(CodeFingerprint).where(CodeFingerprint.document_id == document_id))
    db.execute(delete(CodeUnit).where(CodeUnit.document_id == document_id))
    db.execute(delete(CodeDocument).where(CodeDocument.id == document_id))
    if commit:
        db.commit()
