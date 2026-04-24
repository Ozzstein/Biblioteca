"""Tests for knowledge claim and fact models."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from llm_rag.knowledge.models import (
    Claim,
    ClaimCollection,
    ClaimStatus,
    EntityClaim,
    EvidenceReference,
    Fact,
    RelationClaim,
)
from llm_rag.schemas.entities import EntityType, RelationType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def basic_claim() -> Claim:
    return Claim(
        claim_id="claim:lfp-capacity-001",
        statement="LFP shows 170 mAh/g theoretical capacity",
        confidence=0.85,
        source_doc_id="papers/sample-lfp-001",
        evidence_chunk_ids=["papers/sample-lfp-001:chunk-003"],
    )


@pytest.fixture()
def high_confidence_claim() -> Claim:
    return Claim(
        claim_id="claim:lfp-capacity-002",
        statement="LFP capacity is approximately 170 mAh/g",
        confidence=0.95,
        source_doc_id="papers/sample-lfp-001",
        evidence_chunk_ids=["papers/sample-lfp-001:chunk-003", "papers/sample-lfp-001:chunk-007"],
    )


# ---------------------------------------------------------------------------
# Claim validation
# ---------------------------------------------------------------------------

class TestClaim:
    def test_valid_claim(self, basic_claim: Claim) -> None:
        assert basic_claim.claim_id == "claim:lfp-capacity-001"
        assert basic_claim.confidence == 0.85
        assert basic_claim.status == ClaimStatus.CANDIDATE

    def test_claim_requires_statement(self) -> None:
        with pytest.raises(ValidationError):
            Claim(
                claim_id="claim:x",
                statement="",
                confidence=0.5,
                source_doc_id="doc-1",
                evidence_chunk_ids=["chunk-1"],
            )

    def test_claim_requires_evidence_chunk_ids(self) -> None:
        with pytest.raises(ValidationError):
            Claim(
                claim_id="claim:x",
                statement="some claim",
                confidence=0.5,
                source_doc_id="doc-1",
                evidence_chunk_ids=[],
            )

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Claim(
                claim_id="claim:x",
                statement="bad",
                confidence=1.5,
                source_doc_id="doc-1",
                evidence_chunk_ids=["c1"],
            )
        with pytest.raises(ValidationError):
            Claim(
                claim_id="claim:x",
                statement="bad",
                confidence=-0.1,
                source_doc_id="doc-1",
                evidence_chunk_ids=["c1"],
            )

    def test_claim_requires_source_doc_id(self) -> None:
        with pytest.raises(ValidationError):
            Claim(
                claim_id="claim:x",
                statement="some claim",
                confidence=0.5,
                source_doc_id="",
                evidence_chunk_ids=["chunk-1"],
            )

    def test_claim_default_status(self, basic_claim: Claim) -> None:
        assert basic_claim.status == ClaimStatus.CANDIDATE

    def test_claim_custom_status(self) -> None:
        c = Claim(
            claim_id="claim:x",
            statement="disputed claim",
            confidence=0.5,
            source_doc_id="doc-1",
            evidence_chunk_ids=["c1"],
            status=ClaimStatus.DISPUTED,
        )
        assert c.status == ClaimStatus.DISPUTED


# ---------------------------------------------------------------------------
# Evidence reference validation
# ---------------------------------------------------------------------------

class TestEvidenceReference:
    def test_valid_reference(self) -> None:
        ref = EvidenceReference(
            chunk_id="papers/lfp:chunk-003",
            document_id="papers/lfp",
            span_text="LFP shows 170 mAh/g",
            relevance=0.95,
        )
        assert ref.chunk_id == "papers/lfp:chunk-003"
        assert ref.relevance == 0.95

    def test_default_relevance(self) -> None:
        ref = EvidenceReference(chunk_id="c1", document_id="d1")
        assert ref.relevance == 1.0

    def test_evidence_refs_must_match_chunk_ids(self) -> None:
        with pytest.raises(ValidationError, match="evidence_refs reference chunk_ids not in evidence_chunk_ids"):
            Claim(
                claim_id="claim:x",
                statement="test",
                confidence=0.5,
                source_doc_id="doc-1",
                evidence_chunk_ids=["c1"],
                evidence_refs=[EvidenceReference(chunk_id="c999", document_id="doc-1")],
            )

    def test_evidence_refs_subset_valid(self) -> None:
        c = Claim(
            claim_id="claim:x",
            statement="test",
            confidence=0.5,
            source_doc_id="doc-1",
            evidence_chunk_ids=["c1", "c2"],
            evidence_refs=[EvidenceReference(chunk_id="c1", document_id="doc-1")],
        )
        assert len(c.evidence_refs) == 1


# ---------------------------------------------------------------------------
# Fact validation
# ---------------------------------------------------------------------------

class TestFact:
    def test_valid_fact(self) -> None:
        f = Fact(
            claim_id="fact:lfp-001",
            statement="LFP capacity is 170 mAh/g",
            confidence=0.95,
            source_doc_id="papers/lfp",
            evidence_chunk_ids=["c1", "c2"],
        )
        assert f.status == ClaimStatus.VERIFIED
        assert f.confidence >= 0.9

    def test_fact_rejects_low_confidence(self) -> None:
        with pytest.raises(ValidationError, match="confidence >= 0.9"):
            Fact(
                claim_id="fact:x",
                statement="weak claim",
                confidence=0.7,
                source_doc_id="doc-1",
                evidence_chunk_ids=["c1", "c2"],
            )

    def test_fact_requires_multiple_evidence(self) -> None:
        with pytest.raises(ValidationError, match="at least 2 evidence chunks"):
            Fact(
                claim_id="fact:x",
                statement="single source",
                confidence=0.95,
                source_doc_id="doc-1",
                evidence_chunk_ids=["c1"],
            )

    def test_fact_boundary_confidence(self) -> None:
        f = Fact(
            claim_id="fact:boundary",
            statement="boundary test",
            confidence=0.9,
            source_doc_id="doc-1",
            evidence_chunk_ids=["c1", "c2"],
        )
        assert f.confidence == 0.9


# ---------------------------------------------------------------------------
# EntityClaim and RelationClaim
# ---------------------------------------------------------------------------

class TestEntityClaim:
    def test_valid_entity_claim(self) -> None:
        ec = EntityClaim(
            claim_id="claim:lfp-cap",
            statement="LFP has 170 mAh/g capacity",
            confidence=0.88,
            source_doc_id="papers/lfp",
            evidence_chunk_ids=["c1"],
            entity_id="material:lfp",
            entity_type=EntityType.MATERIAL,
            property_name="capacity_mah_g",
            property_value="170",
        )
        assert ec.entity_id == "material:lfp"
        assert ec.entity_type == EntityType.MATERIAL

    def test_entity_claim_requires_entity_id(self) -> None:
        with pytest.raises(ValidationError):
            EntityClaim(
                claim_id="claim:x",
                statement="test",
                confidence=0.5,
                source_doc_id="d1",
                evidence_chunk_ids=["c1"],
                entity_id="",
                entity_type=EntityType.MATERIAL,
                property_name="capacity",
                property_value="170",
            )


class TestRelationClaim:
    def test_valid_relation_claim(self) -> None:
        rc = RelationClaim(
            claim_id="claim:sei-causes-fade",
            statement="SEI growth causes capacity fade in LFP",
            confidence=0.82,
            source_doc_id="papers/sei-study",
            evidence_chunk_ids=["c5"],
            source_entity_id="mechanism:sei",
            target_entity_id="mechanism:capacity-fade",
            relation_type=RelationType.CAUSES,
        )
        assert rc.source_entity_id == "mechanism:sei"
        assert rc.relation_type == RelationType.CAUSES

    def test_relation_claim_requires_entities(self) -> None:
        with pytest.raises(ValidationError):
            RelationClaim(
                claim_id="claim:x",
                statement="test",
                confidence=0.5,
                source_doc_id="d1",
                evidence_chunk_ids=["c1"],
                source_entity_id="",
                target_entity_id="e2",
                relation_type=RelationType.AFFECTS,
            )


# ---------------------------------------------------------------------------
# ClaimCollection
# ---------------------------------------------------------------------------

class TestClaimCollection:
    def test_empty_collection(self) -> None:
        cc = ClaimCollection(source_doc_id="papers/lfp")
        assert cc.total_claims == 0
        assert cc.facts == []

    def test_collection_with_claims(self, basic_claim: Claim) -> None:
        cc = ClaimCollection(source_doc_id="papers/sample-lfp-001", claims=[basic_claim])
        assert cc.total_claims == 1

    def test_collection_doc_consistency(self, basic_claim: Claim) -> None:
        with pytest.raises(ValidationError, match="mismatched source_doc_id"):
            ClaimCollection(source_doc_id="papers/other-doc", claims=[basic_claim])

    def test_facts_property(self, high_confidence_claim: Claim) -> None:
        cc = ClaimCollection(
            source_doc_id="papers/sample-lfp-001",
            claims=[high_confidence_claim],
        )
        assert len(cc.facts) == 1
        assert cc.facts[0].claim_id == "claim:lfp-capacity-002"

    def test_facts_filters_low_confidence(self, basic_claim: Claim) -> None:
        cc = ClaimCollection(source_doc_id="papers/sample-lfp-001", claims=[basic_claim])
        assert len(cc.facts) == 0

    def test_total_claims_all_types(self) -> None:
        cc = ClaimCollection(
            source_doc_id="doc-1",
            claims=[
                Claim(claim_id="c1", statement="s1", confidence=0.5, source_doc_id="doc-1", evidence_chunk_ids=["e1"]),
            ],
            entity_claims=[
                EntityClaim(
                    claim_id="ec1", statement="s2", confidence=0.6, source_doc_id="doc-1",
                    evidence_chunk_ids=["e2"], entity_id="material:x", entity_type=EntityType.MATERIAL,
                    property_name="p", property_value="v",
                ),
            ],
            relation_claims=[
                RelationClaim(
                    claim_id="rc1", statement="s3", confidence=0.7, source_doc_id="doc-1",
                    evidence_chunk_ids=["e3"], source_entity_id="a", target_entity_id="b",
                    relation_type=RelationType.AFFECTS,
                ),
            ],
        )
        assert cc.total_claims == 3


# ---------------------------------------------------------------------------
# Roundtrip serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_claim_roundtrip(self, basic_claim: Claim) -> None:
        json_str = basic_claim.model_dump_json()
        restored = Claim.model_validate_json(json_str)
        assert restored.claim_id == basic_claim.claim_id
        assert restored.confidence == basic_claim.confidence
        assert restored.evidence_chunk_ids == basic_claim.evidence_chunk_ids

    def test_fact_roundtrip(self) -> None:
        f = Fact(
            claim_id="fact:rt",
            statement="roundtrip test",
            confidence=0.95,
            source_doc_id="doc-1",
            evidence_chunk_ids=["c1", "c2"],
        )
        restored = Fact.model_validate_json(f.model_dump_json())
        assert restored.status == ClaimStatus.VERIFIED

    def test_entity_claim_roundtrip(self) -> None:
        ec = EntityClaim(
            claim_id="ec:rt",
            statement="entity roundtrip",
            confidence=0.8,
            source_doc_id="doc-1",
            evidence_chunk_ids=["c1"],
            entity_id="material:lfp",
            entity_type=EntityType.MATERIAL,
            property_name="capacity",
            property_value="170",
        )
        restored = EntityClaim.model_validate_json(ec.model_dump_json())
        assert restored.entity_id == "material:lfp"
        assert restored.entity_type == EntityType.MATERIAL

    def test_relation_claim_roundtrip(self) -> None:
        rc = RelationClaim(
            claim_id="rc:rt",
            statement="relation roundtrip",
            confidence=0.75,
            source_doc_id="doc-1",
            evidence_chunk_ids=["c1"],
            source_entity_id="mechanism:sei",
            target_entity_id="mechanism:fade",
            relation_type=RelationType.CAUSES,
        )
        restored = RelationClaim.model_validate_json(rc.model_dump_json())
        assert restored.relation_type == RelationType.CAUSES

    def test_collection_roundtrip(self, basic_claim: Claim) -> None:
        cc = ClaimCollection(source_doc_id="papers/sample-lfp-001", claims=[basic_claim])
        json_str = cc.to_json()
        restored = ClaimCollection.model_validate_json(json_str)
        assert restored.total_claims == 1
        assert restored.claims[0].claim_id == basic_claim.claim_id

    def test_collection_json_is_valid(self, basic_claim: Claim) -> None:
        cc = ClaimCollection(source_doc_id="papers/sample-lfp-001", claims=[basic_claim])
        parsed = json.loads(cc.to_json())
        assert parsed["source_doc_id"] == "papers/sample-lfp-001"
        assert len(parsed["claims"]) == 1
