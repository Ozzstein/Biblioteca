from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfPage:
    page_number: int
    text: str
    tables: list[list[list[str | None]]]


def extract_pages(path: Path) -> list[PdfPage]:
    """Extract text and tables from a PDF using pdfplumber."""
    import pdfplumber  # lazy import — heavy dependency

    pages: list[PdfPage] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            pages.append(PdfPage(page_number=i + 1, text=text, tables=tables))
    return pages
