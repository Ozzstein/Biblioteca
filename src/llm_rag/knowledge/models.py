"""First-class claim and fact schemas for extracted assertions.

These models elevate claims from implicit graph/wiki artifacts to
explicit, evidence-linked knowledge objects with confidence tracking
and full provenance.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from llm_rag.schemas.entities import EntityType, RelationType


class ClaimStatus(StrEnum):
    """Lifecycle status of a claim."""

    CANDIDATE = "candidate"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    RETRACTED = "retracted"


class EvidenceReference(BaseModel):
    """Pointer to a specific piece of evidence supporting or contradicting a claim."""

    chunk_id: str = Field(min_length=1, description="Evidence chunk identifier")
    document_id: str = Field(min_length=1, description="Source document identifier")
    span_text: str | None = Field(default=None, description="Verbatim text excerpt from the source")
    relevance: float = Field(ge=0.0, le=1.0, default=1.0, description="How relevant this evidence is to the claim")


class Claim(BaseModel):
    """An assertion extracted from the corpus with confidence and evidence references.

    Every claim must reference at least one evidence chunk so that
    provenance is never lost.
    """

    claim_id: str = Field(min_length=1, description="Unique claim identifier, e.g. 'claim:lfp-capacity-001'")
    statement: str = Field(min_length=1, description="The assertion text")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for the claim")
    source_doc_id: str = Field(min_length=1, description="Primary source document ID")
    evidence_chunk_ids: list[str] = Field(min_length=1, description="Evidence chunk IDs supporting this claim")
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list, description="Detailed evidence references with provenance"
    )
    status: ClaimStatus = Field(default=ClaimStatus.CANDIDATE, description="Lifecycle status")
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="When the claim was extracted")
    metadata: dict[str, str] = Field(default_factory=dict, description="Additional key-value metadata")

    @model_validator(mode="after")
    def _evidence_refs_match_chunk_ids(self) -> Claim:
        """If evidence_refs are provided, their chunk_ids must be a subset of evidence_chunk_ids."""
        if self.evidence_refs:
            ref_chunk_ids = {ref.chunk_id for ref in self.evidence_refs}
            allowed = set(self.evidence_chunk_ids)
            extra = ref_chunk_ids - allowed
            if extra:
                msg = f"evidence_refs reference chunk_ids not in evidence_chunk_ids: {extra}"
                raise ValueError(msg)
        return self


class Fact(Claim):
    """A verified claim with high confidence and multiple evidence sources.

    A Fact is a Claim that has been corroborated: confidence >= 0.9
    and evidence from at least 2 distinct chunks.
    """

    status: ClaimStatus = Field(default=ClaimStatus.VERIFIED)

    @model_validator(mode="after")
    def _validate_fact_requirements(self) -> Fact:
        if self.confidence < 0.9:
            msg = f"Fact requires confidence >= 0.9, got {self.confidence}"
            raise ValueError(msg)
        if len(self.evidence_chunk_ids) < 2:
            msg = f"Fact requires at least 2 evidence chunks, got {len(self.evidence_chunk_ids)}"
            raise ValueError(msg)
        return self


class EntityClaim(Claim):
    """A claim about a specific entity's properties."""

    entity_id: str = Field(min_length=1, description="Target entity ID, e.g. 'material:lfp'")
    entity_type: EntityType = Field(description="Type of the target entity")
    property_name: str = Field(min_length=1, description="Property being claimed, e.g. 'capacity_mah_g'")
    property_value: str = Field(min_length=1, description="Claimed value, e.g. '170'")


class RelationClaim(Claim):
    """A claim asserting a relation between two entities."""

    source_entity_id: str = Field(min_length=1, description="Source entity ID")
    target_entity_id: str = Field(min_length=1, description="Target entity ID")
    relation_type: RelationType = Field(description="Type of the asserted relation")


class ClaimCollection(BaseModel):
    """Container for all claims extracted from a single document."""

    source_doc_id: str = Field(min_length=1, description="Document these claims were extracted from")
    claims: list[Claim] = Field(default_factory=list)
    entity_claims: list[EntityClaim] = Field(default_factory=list)
    relation_claims: list[RelationClaim] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def _validate_doc_consistency(self) -> ClaimCollection:
        """All claims must reference the same source document."""
        all_claims: list[Claim] = [*self.claims, *self.entity_claims, *self.relation_claims]
        mismatched = [c.claim_id for c in all_claims if c.source_doc_id != self.source_doc_id]
        if mismatched:
            msg = f"Claims with mismatched source_doc_id: {mismatched}"
            raise ValueError(msg)
        return self

    @property
    def total_claims(self) -> int:
        return len(self.claims) + len(self.entity_claims) + len(self.relation_claims)

    @property
    def facts(self) -> list[Claim]:
        """Return only claims that meet Fact-level thresholds."""
        return [
            c
            for c in [*self.claims, *self.entity_claims, *self.relation_claims]
            if c.confidence >= 0.9 and len(c.evidence_chunk_ids) >= 2
        ]

    def to_json(self) -> str:
        """Deterministic JSON serialization."""
        return self.model_dump_json(indent=2)
