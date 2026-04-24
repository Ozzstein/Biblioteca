from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ExtractionMethod(StrEnum):
    CLAUDE_HAIKU = "claude-haiku"
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    RULE_BASED = "rule-based"
    MANUAL = "manual"


class ProvenanceRecord(BaseModel):
    source_doc_id: str
    source_path: str
    section: str | None = None
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: ExtractionMethod
    extractor_model: str | None = None


class ProcessingStage(StrEnum):
    INGESTED = "ingested"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    WIKI_COMPILED = "wiki_compiled"
    GRAPH_UPDATED = "graph_updated"


class FailedStageRecord(BaseModel):
    """Tracks a stage that has exhausted retries (dead-letter)."""

    stage: ProcessingStage
    attempts: int
    last_error: str
    failed_at: datetime


class DocumentManifest(BaseModel):
    doc_id: str
    source_path: str
    content_hash: str
    doc_type: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    arxiv_id: str | None = None
    source_connector: str
    fetched_at: datetime
    stages_completed: list[ProcessingStage] = Field(default_factory=list)
    last_processed: datetime
    error: str | None = None
    failed_stages: list[FailedStageRecord] = Field(default_factory=list)
