from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


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


class DocType(StrEnum):
    PAPER = "paper"
    SOP = "sop"
    REPORT = "report"
    MEETING = "meeting"
    UNKNOWN = "unknown"


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
    doc_type: DocType
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

    @field_validator("doc_type", mode="before")
    @classmethod
    def _resolve_doc_type_alias(cls, value: object) -> DocType | object:
        if isinstance(value, DocType):
            return value
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        alias_map = {
            "paper": DocType.PAPER,
            "papers": DocType.PAPER,
            "sop": DocType.SOP,
            "sops": DocType.SOP,
            "report": DocType.REPORT,
            "reports": DocType.REPORT,
            "meeting": DocType.MEETING,
            "meetings": DocType.MEETING,
        }
        return alias_map.get(normalized, DocType.UNKNOWN)
