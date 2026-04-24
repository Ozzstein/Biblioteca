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
