"""Typed interfaces for core pipeline artifacts.

These Pydantic models define the contracts between pipeline stages,
ensuring type-safe data flow from ingestion through query response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from llm_rag.schemas.entities import EntityType, RelationType
from llm_rag.schemas.provenance import DocType

__all__ = [
    "ClaimCandidate",
    "EvidenceChunk",
    "ExtractedEntity",
    "ExtractedRelation",
    "GraphPatch",
    "QueryCitation",
    "QueryResultBundle",
    "SourceDocument",
    "WikiPageDraft",
]


class SourceDocument(BaseModel):
    """Document metadata produced by the ingestion stage."""

    doc_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    doc_type: DocType
    content_hash: str = Field(min_length=1)
    ingested_at: datetime


class EvidenceChunk(BaseModel):
    """Chunked text with provenance linking back to a source document."""

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    embedding: list[float] | None = None


class ExtractedEntity(BaseModel):
    """Entity extracted from source chunks by the extraction stage."""

    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    entity_type: EntityType
    aliases: list[str] = Field(default_factory=list)
    source_chunks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedRelation(BaseModel):
    """Directed relation between two extracted entities."""

    relation_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    predicate: RelationType
    object_id: str = Field(min_length=1)
    source_chunks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ClaimCandidate(BaseModel):
    """Candidate claim or factual statement extracted from the corpus."""

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    supporting_entities: list[str] = Field(default_factory=list)
    source_chunks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class WikiPageDraft(BaseModel):
    """Draft wiki page structure for the wiki compilation stage."""

    entity_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    sections: dict[str, str] = Field(default_factory=dict)
    auto_sections: list[str] = Field(default_factory=list)
    human_sections: list[str] = Field(default_factory=list)


class GraphPatch(BaseModel):
    """Batch of graph mutation operations applied by the graph curator."""

    add_nodes: list[dict[str, Any]] = Field(default_factory=list)
    add_edges: list[dict[str, Any]] = Field(default_factory=list)
    remove_nodes: list[str] = Field(default_factory=list)
    remove_edges: list[dict[str, str]] = Field(default_factory=list)


class QueryCitation(BaseModel):
    """Citation linking a query answer back to a source."""

    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    relevance_score: float = Field(ge=0.0, le=1.0)
    provenance_path: str = Field(min_length=1)


class QueryResultBundle(BaseModel):
    """Complete query response with citations and metadata."""

    answer: str = Field(min_length=1)
    citations: list[QueryCitation] = Field(default_factory=list)
    routing_mode: str = Field(min_length=1)
    processing_time_ms: float = Field(ge=0.0)
