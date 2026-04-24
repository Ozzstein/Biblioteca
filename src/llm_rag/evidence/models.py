"""Canonical evidence-record schemas.

These models are the internal source of truth for document and evidence
storage. They provide deterministic serialization (sorted keys, stable
field order) so that identical inputs always produce identical outputs.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class DocumentType(StrEnum):
    PAPER = "paper"
    REPORT = "report"
    DATASET = "dataset"
    SIMULATION = "simulation"
    MEETING = "meeting"
    SOP = "sop"
    URL = "url"
    OTHER = "other"


class ProvenanceSpan(BaseModel):
    """Locates a chunk within its source document.

    Tracks byte offsets, page numbers, and section names so that any
    extracted fact can be traced back to its exact origin.
    """

    start_byte: int = Field(ge=0, description="Start byte offset in the source document")
    end_byte: int = Field(gt=0, description="End byte offset (exclusive) in the source document")
    page_start: int | None = Field(default=None, ge=1, description="Starting page number (1-based)")
    page_end: int | None = Field(default=None, ge=1, description="Ending page number (1-based, inclusive)")
    section_name: str | None = Field(default=None, description="Section heading the span falls under")

    @model_validator(mode="after")
    def _validate_offsets(self) -> ProvenanceSpan:
        if self.end_byte <= self.start_byte:
            msg = f"end_byte ({self.end_byte}) must be greater than start_byte ({self.start_byte})"
            raise ValueError(msg)
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            msg = f"page_end ({self.page_end}) must be >= page_start ({self.page_start})"
            raise ValueError(msg)
        return self

    @property
    def byte_length(self) -> int:
        return self.end_byte - self.start_byte


class EvidenceChunk(BaseModel):
    """Canonical chunk record with provenance linking back to source."""

    chunk_id: str = Field(min_length=1, description="Unique chunk identifier, e.g. 'papers/sample-lfp-001:chunk-003'")
    document_id: str = Field(min_length=1, description="Parent document ID")
    text: str = Field(min_length=1, description="Chunk text content")
    content_hash: str = Field(min_length=1, description="sha256:<hex> hash of text for deduplication")
    span: ProvenanceSpan = Field(description="Location of this chunk in the source document")
    chunk_index: int = Field(ge=0, description="Zero-based index of this chunk within the document")
    token_estimate: int = Field(ge=0, description="Approximate token count (len(text) // 4)")
    embedding: list[float] | None = Field(default=None, description="Optional embedding vector")
    metadata: dict[str, str] = Field(default_factory=dict, description="Additional key-value metadata")

    @staticmethod
    def hash_text(text: str) -> str:
        """Compute a deterministic content hash for chunk text."""
        return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"

    model_config = {"frozen": False}


class EvidenceDocument(BaseModel):
    """Canonical document record with full metadata.

    This is the definitive record for a source document. It captures
    provenance metadata (origin, authors, identifiers) and processing
    state (content hash, ingestion timestamp).
    """

    doc_id: str = Field(min_length=1, description="Stable document identifier, e.g. 'papers/sample-lfp-001'")
    source_path: str = Field(min_length=1, description="Path to source file relative to raw/")
    doc_type: DocumentType = Field(description="Document classification")
    content_hash: str = Field(min_length=1, description="sha256:<hex> hash of the source file")
    title: str | None = Field(default=None, description="Document title")
    authors: list[str] = Field(default_factory=list, description="Author names")
    doi: str | None = Field(default=None, description="DOI identifier")
    arxiv_id: str | None = Field(default=None, description="arXiv identifier")
    source_connector: str | None = Field(default=None, description="Subagent that fetched this document")
    ingested_at: datetime = Field(description="Timestamp when the document was ingested")
    page_count: int | None = Field(default=None, ge=1, description="Total pages (for PDFs)")
    byte_size: int | None = Field(default=None, ge=0, description="File size in bytes")
    metadata: dict[str, str] = Field(default_factory=dict, description="Additional key-value metadata")


class EvidenceStore(BaseModel):
    """Container for all evidence from a single processed document.

    This is the canonical source-of-truth for a document's evidence:
    the document record plus all its chunks with provenance spans.
    Serialization is deterministic — same input always produces the
    same JSON output.
    """

    document: EvidenceDocument = Field(description="The source document record")
    chunks: list[EvidenceChunk] = Field(default_factory=list, description="Ordered list of chunks")

    @model_validator(mode="after")
    def _validate_chunk_ownership(self) -> EvidenceStore:
        for chunk in self.chunks:
            if chunk.document_id != self.document.doc_id:
                msg = (
                    f"Chunk '{chunk.chunk_id}' has document_id '{chunk.document_id}' "
                    f"but store document is '{self.document.doc_id}'"
                )
                raise ValueError(msg)
        return self

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def total_tokens(self) -> int:
        return sum(c.token_estimate for c in self.chunks)

    def get_chunk(self, chunk_id: str) -> EvidenceChunk | None:
        """Look up a chunk by ID. Returns None if not found."""
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        return None

    def to_json(self) -> str:
        """Deterministic JSON serialization (sorted keys)."""
        return self.model_dump_json(indent=2)

    model_config = {"json_schema_serialization_defaults_required": True}
