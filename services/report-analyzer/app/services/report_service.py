from dataclasses import asdict

from sqlalchemy.orm import Session

from app.analyzers.consistency import check_consistency
from app.analyzers.documentation import evaluate_documentation
from app.analyzers.plagiarism import check_and_index
from app.parsers.extract import extract

MIN_WORDS = 50


def analyze_report(
    db: Session, document_id: str, data: bytes, filename: str, facts: dict | None, index: bool
) -> dict:
    document = extract(data, filename)
    text = document.text
    documentation = evaluate_documentation(document)
    warnings = []
    if documentation["word_count"] < MIN_WORDS:
        warnings.append(
            "Almost no text could be extracted; the report may be scanned images. "
            "Plagiarism and consistency results are unreliable."
        )

    plagiarism = check_and_index(db, document_id, text, index=index and bool(text.strip()))
    consistency = check_consistency(text, facts)

    # Starting weights, to be tuned against faculty grades later.
    originality = max(0.0, 100 - plagiarism.plagiarism_percentage)
    penalty = sum(15 if i["severity"] == "Medium" else 5 for i in consistency["inconsistencies"])
    consistency_score = max(0.0, 100.0 - penalty) if consistency["checked"] else None
    parts = [(documentation["documentation_quality_score"], 0.5), (originality, 0.35)]
    if consistency_score is not None:
        parts.append((consistency_score, 0.15))
    overall = sum(score * weight for score, weight in parts) / sum(w for _, w in parts)

    return {
        "format": document.format,
        "warnings": warnings,
        "plagiarism": asdict(plagiarism),
        "consistency": {**consistency, "consistency_score": consistency_score},
        "documentation": documentation,
        "overall_report_score": round(overall, 1),
    }
