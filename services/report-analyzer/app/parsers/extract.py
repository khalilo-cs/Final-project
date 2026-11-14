"""Text extraction from PDF and DOCX reports."""

import contextlib
import io
import zipfile
from dataclasses import dataclass, field

from app.config import get_settings
from app.text.normalize import clean_extracted


class ExtractionError(Exception):
    pass


@dataclass
class Paragraph:
    text: str
    is_heading: bool = False


@dataclass
class ExtractedDocument:
    format: str
    paragraphs: list[Paragraph] = field(default_factory=list)
    pages: int | None = None
    images: int = 0
    tables: int = 0

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.paragraphs)


def extract(data: bytes, filename: str) -> ExtractedDocument:
    name = filename.lower()
    if name.endswith(".pdf"):
        return _pdf(data)
    if name.endswith(".docx"):
        return _docx(data)
    raise ExtractionError("Only PDF and DOCX reports are supported")


def _pdf(data: bytes) -> ExtractedDocument:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    settings = get_settings()
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("The PDF is password protected")
        pages = reader.pages
        if len(pages) > settings.max_pages:
            raise ExtractionError(f"The PDF has more than {settings.max_pages} pages")
        document = ExtractedDocument(format="pdf", pages=len(pages))
        for page in pages:
            text = clean_extracted(page.extract_text() or "")
            document.paragraphs.extend(
                Paragraph(line.strip()) for line in text.splitlines() if line.strip()
            )
            # Broken embedded images must not fail text extraction.
            with contextlib.suppress(Exception):
                document.images += len(page.images)
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise ExtractionError(f"Could not read the PDF ({type(exc).__name__})") from exc
    return document


def _docx(data: bytes) -> ExtractedDocument:
    from docx import Document

    limit = get_settings().max_docx_uncompressed_mb * 1024 * 1024
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            if sum(info.file_size for info in bundle.infolist()) > limit:
                raise ExtractionError("The DOCX is too large when uncompressed")
            images = sum(1 for n in bundle.namelist() if n.startswith("word/media/"))
        word = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ExtractionError("Could not read the DOCX file") from exc

    document = ExtractedDocument(format="docx", images=images, tables=len(word.tables))
    for paragraph in word.paragraphs:
        text = clean_extracted(paragraph.text).strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        heading = style.lower().startswith(("heading", "title", "عنوان"))
        document.paragraphs.append(Paragraph(text, heading))
    for table in word.tables:
        for row in table.rows:
            cells = [clean_extracted(cell.text).strip() for cell in row.cells]
            line = " | ".join(dict.fromkeys(c for c in cells if c))
            if line:
                document.paragraphs.append(Paragraph(line))
    return document
