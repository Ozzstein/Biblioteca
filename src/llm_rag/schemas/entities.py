from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from llm_rag.schemas.provenance import ProvenanceRecord


class EntityType(StrEnum):
    DOCUMENT = "Document"
    PROJECT = "Project"
    MATERIAL = "Material"
    PROCESS = "Process"
    COMPONENT = "Component"
    FORMULATION = "Formulation"
    CELL = "Cell"
    TEST_CONDITION = "TestCondition"
    METRIC = "Metric"
    PROPERTY = "Property"
    FAILURE_MECHANISM = "FailureMechanism"
    DATASET = "Dataset"
    EXPERIMENT = "Experiment"
    CLAIM = "Claim"
    SOP = "SOP"
    MEETING = "Meeting"
    INTERNAL_REPORT = "InternalReport"


class RelationType(StrEnum):
    MENTIONS = "MENTIONS"
    USES_MATERIAL = "USES_MATERIAL"
    USES_PROCESS = "USES_PROCESS"
    PRODUCES_PROPERTY = "PRODUCES_PROPERTY"
    MEASURED_BY = "MEASURED_BY"
    TESTED_UNDER = "TESTED_UNDER"
    AFFECTS = "AFFECTS"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    CAUSES = "CAUSES"
    MITIGATES = "MITIGATES"
    CONTRADICTS = "CONTRADICTS"
    SUPPORTED_BY = "SUPPORTED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    PART_OF = "PART_OF"
    SIMULATED_BY = "SIMULATED_BY"


class Entity(BaseModel):
    entity_id: str
    entity_type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    wiki_page: str | None = None


class Material(Entity):
    entity_type: Literal[EntityType.MATERIAL] = EntityType.MATERIAL
    formula: str | None = None
    material_class: str | None = None
    crystal_structure: str | None = None


class Cell(Entity):
    entity_type: Literal[EntityType.CELL] = EntityType.CELL
    chemistry: str | None = None
    form_factor: str | None = None
    capacity_mah: float | None = None


class Claim(Entity):
    entity_type: Literal[EntityType.CLAIM] = EntityType.CLAIM
    statement: str
    supported_by: list[str] = Field(default_factory=list)
    contradicted_by: list[str] = Field(default_factory=list)


LabStatus = Literal["approved", "draft", "superseded", "unknown"]


class Sop(Entity):
    entity_type: Literal[EntityType.SOP] = EntityType.SOP
    status: LabStatus = "unknown"
    effective_date: str | None = None
    superseded_by: str | None = None
    ingested_at: datetime | None = None
    source_url: str | None = None
    sop_id: str | None = None
    version: str | None = None
    supersedes: str | None = None
    procedure_steps: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    safety_notes: str | None = None
    scope: str | None = None
    deprecated: bool = False


class Meeting(Entity):
    entity_type: Literal[EntityType.MEETING] = EntityType.MEETING
    status: LabStatus = "unknown"
    effective_date: str | None = None
    superseded_by: str | None = None
    ingested_at: datetime | None = None
    source_url: str | None = None
    attendees: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)


class InternalReport(Entity):
    entity_type: Literal[EntityType.INTERNAL_REPORT] = EntityType.INTERNAL_REPORT
    status: LabStatus = "unknown"
    effective_date: str | None = None
    superseded_by: str | None = None
    ingested_at: datetime | None = None
    source_url: str | None = None
    report_id: str | None = None
    authors: list[str] = Field(default_factory=list)
    period_covered: str | None = None
    key_metrics: dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    relation_id: str
    relation_type: RelationType
    source_entity_id: str
    target_entity_id: str
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    weight: float = 1.0


class ExtractionResult(BaseModel):
    doc_id: str
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    chunks_processed: int = 0
    extraction_model: str
    extracted_at: datetime
