"""Documentation quality (FR-06.6): structure, references, length, figures."""

import re

from app.parsers.extract import ExtractedDocument
from app.text.normalize import normalize

# Chapters expected in a project report (Arabic or English headings).
SECTIONS = {
    "introduction": [r"مقدمه", r"\bintroduction\b"],
    "problem_statement": [r"مشكله\s*البحث", r"المشكله", r"problem\s*statement"],
    "objectives": [r"الاهداف", r"اهداف", r"\bobjectives?\b", r"\baims?\b"],
    "literature_review": [
        r"الدراسات\s*السابقه",
        r"الانظمه\s*المشابهه",
        r"literature\s*review",
        r"related\s*work",
    ],  # fmt: skip
    "requirements": [r"المتطلبات", r"\brequirements\b"],
    "design": [r"التصميم", r"تصميم\s*النظام", r"system\s*design", r"\bdesign\b"],
    "implementation": [r"التنفيذ", r"التطبيق\s*العملي", r"\bimplementation\b"],
    "testing": [r"الاختبار", r"\btesting\b", r"\bevaluation\b"],
    "conclusion": [r"الخاتمه", r"الخلاصه", r"الاستنتاج", r"\bconclusions?\b"],
    "references": [r"المراجع", r"المصادر", r"\breferences\b", r"\bbibliography\b"],
}
_NUMBERING = re.compile(r"^\s*(?:(?:chapter|الفصل)\s+\S+\s*[:.\-]?\s*)?[\d.\-)\s]*")
_CAPTION = re.compile(r"^\s*(?:figure|fig\.|table|شكل|الشكل|جدول|الجدول)\s*(?:رقم\s*)?\(?\d")
_REFERENCE_LINE = re.compile(r"(?:^\s*\[\d+\])|(?:\((?:19|20)\d{2}\))|(?:\b(?:19|20)\d{2}\b.*\.)")


def _heading_like(paragraph) -> bool:
    return paragraph.is_heading or len(paragraph.text) <= 80


def evaluate_documentation(document: ExtractedDocument) -> dict:
    found: dict[str, int] = {}
    references_start = None
    for index, paragraph in enumerate(document.paragraphs):
        if not _heading_like(paragraph):
            continue
        heading = _NUMBERING.sub("", normalize(paragraph.text)).strip()
        for section, patterns in SECTIONS.items():
            if section in found:
                continue
            if any(re.match(pattern, heading) for pattern in patterns):
                found[section] = index
                if section == "references":
                    references_start = index
                break

    references = 0
    if references_start is not None:
        references = sum(
            1
            for paragraph in document.paragraphs[references_start + 1 :]
            if _REFERENCE_LINE.search(paragraph.text)
        )
    captions = sum(1 for p in document.paragraphs if _CAPTION.match(normalize(p.text)))
    words = len(document.text.split())

    section_score = 50 * len(found) / len(SECTIONS)
    reference_score = 20 * min(references, 10) / 10
    length_score = 15 * min(words, 6000) / 6000
    figure_score = 15 * min(captions + document.images, 5) / 5
    missing = [section for section in SECTIONS if section not in found]
    return {
        "word_count": words,
        "pages": document.pages,
        "sections_found": sorted(found, key=found.get),
        "sections_missing": missing,
        "references_count": references,
        "figure_and_table_captions": captions,
        "images": document.images,
        "documentation_quality_score": round(
            section_score + reference_score + length_score + figure_score, 1
        ),
    }
