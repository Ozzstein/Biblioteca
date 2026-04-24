from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    doc_id: str
    chunk_index: int
    text: str
    section: str | None
    page: int | None
    token_count: int


def chunk_text(
    text: str,
    doc_id: str,
    chunk_size: int = 512,
    overlap: int = 64,
    section: str | None = None,
    page: int | None = None,
) -> list[Chunk]:
    """Split text into overlapping chunks. Token count approximated as len(text) // 4."""
    if not text:
        return []

    char_size = chunk_size * 4
    char_overlap = overlap * 4
    chunks: list[Chunk] = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + char_size, len(text))
        content = text[start:end]
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_index=idx,
                text=content,
                section=section,
                page=page,
                token_count=len(content) // 4,
            )
        )
        if end == len(text):
            break
        start += char_size - char_overlap
        idx += 1

    return chunks
