"""Tests for GraphMaterializer — graph as a projection from claims/facts."""

from __future__ import annotations

import pytest

from llm_rag.graph.materializer import GraphMaterializer
from llm_rag.knowledge.models import (
    ClaimCollection,
    EntityClaim,
    RelationClaim,
)
from llm_rag.schemas.entities import EntityType, RelationType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entity_claim(
    *,
    claim_id: str = "ec-1",
    entity_id: str = "material:lfp",
    entity_type: EntityType = EntityType.MATERIAL,
    property_name: str = "formula",
    property_value: str = "LiFePO4",
    confidence: float = 0.95,
    evidence_chunk_ids: list[str] | None = None,
    source_doc_id: str = "papers/sample-001",
) -> EntityClaim:
    return EntityClaim(
        claim_id=claim_id,
        statement=f"{entity_id} has {property_name}={property_value}",
        confidence=confidence,
        source_doc_id=source_doc_id,
        evidence_chunk_ids=evidence_chunk_ids or ["c1", "c2"],
        entity_id=entity_id,
        entity_type=entity_type,
        property_name=property_name,
        property_value=property_value,
    )


def _relation_claim(
    *,
    claim_id: str = "rc-1",
    source_entity_id: str = "material:lfp",
    target_entity_id: str = "mechanism:sei",
    relation_type: RelationType = RelationType.CAUSES,
    confidence: float = 0.92,
    evidence_chunk_ids: list[str] | None = None,
    source_doc_id: str = "papers/sample-001",
) -> RelationClaim:
    return RelationClaim(
        claim_id=claim_id,
        statement=f"{source_entity_id} {relation_type} {target_entity_id}",
        confidence=confidence,
        source_doc_id=source_doc_id,
        evidence_chunk_ids=evidence_chunk_ids or ["c1", "c2"],
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relation_type=relation_type,
    )


# ---------------------------------------------------------------------------
# Tests: build_graph_from_claims
# ---------------------------------------------------------------------------


class TestBuildGraphFromClaims:
    def test_entities_become_nodes(self) -> None:
        ec = _entity_claim()
        mat = GraphMaterializer()
        g = mat.build_graph_from_claims([ec], [])

        assert g.has_node("material:lfp")
        assert g.nodes["material:lfp"]["entity_type"] == "Material"
        assert g.nodes["material:lfp"]["prop:formula"] == "LiFePO4"

    def test_relations_become_edges(self) -> None:
        rc = _relation_claim()
        mat = GraphMaterializer()
        g = mat.build_graph_from_claims([], [rc])

        assert g.has_edge("material:lfp", "mechanism:sei")
        edges = g.get_edge_data("material:lfp", "mechanism:sei")
        assert edges is not None
        assert edges["rc-1"]["relation_type"] == "CAUSES"

    def test_relation_creates_stub_nodes(self) -> None:
        """Relation endpoints that have no EntityClaim get stub nodes."""
        rc = _relation_claim()
        mat = GraphMaterializer()
        g = mat.build_graph_from_claims([], [rc])

        assert g.has_node("material:lfp")
        assert g.has_node("mechanism:sei")
        # Stub nodes have empty entity_type
        assert g.nodes["material:lfp"]["entity_type"] == ""

    def test_entity_claim_enriches_stub(self) -> None:
        """EntityClaim added before relation should survive as a real node."""
        ec = _entity_claim(entity_id="material:lfp")
        rc = _relation_claim(source_entity_id="material:lfp")
        mat = GraphMaterializer()
        g = mat.build_graph_from_claims([ec], [rc])

        # Entity should retain its type, not be overwritten by stub
        assert g.nodes["material:lfp"]["entity_type"] == "Material"

    def test_multiple_claims_merge_on_same_entity(self) -> None:
        ec1 = _entity_claim(claim_id="ec-1", property_name="formula", property_value="LiFePO4")
        ec2 = _entity_claim(
            claim_id="ec-2",
            property_name="crystal_structure",
            property_value="olivine",
            confidence=0.98,
        )
        mat = GraphMaterializer()
        g = mat.build_graph_from_claims([ec1, ec2], [])

        assert g.number_of_nodes() == 1
        node = g.nodes["material:lfp"]
        assert node["prop:formula"] == "LiFePO4"
        assert node["prop:crystal_structure"] == "olivine"
        # Confidence should be max of both
        assert node["confidence"] == 0.98

    def test_empty_input_produces_empty_graph(self) -> None:
        mat = GraphMaterializer()
        g = mat.build_graph_from_claims([], [])
        assert g.number_of_nodes() == 0
        assert g.number_of_edges() == 0


# ---------------------------------------------------------------------------
# Tests: build_graph_from_facts (high-confidence filter)
# ---------------------------------------------------------------------------


class TestBuildGraphFromFacts:
    def test_low_confidence_claims_excluded(self) -> None:
        ec_low = _entity_claim(claim_id="ec-low", confidence=0.5)
        ec_high = _entity_claim(claim_id="ec-high", confidence=0.95, entity_id="material:nmc")
        mat = GraphMaterializer()
        g = mat.build_graph_from_facts([ec_low, ec_high], [])

        assert not g.has_node("material:lfp")
        assert g.has_node("material:nmc")

    def test_insufficient_evidence_excluded(self) -> None:
        ec_sparse = _entity_claim(
            claim_id="ec-sparse",
            confidence=0.95,
            evidence_chunk_ids=["c1"],  # only 1 chunk
        )
        mat = GraphMaterializer()
        g = mat.build_graph_from_facts([ec_sparse], [])
        assert g.number_of_nodes() == 0

    def test_facts_include_qualifying_relations(self) -> None:
        rc_good = _relation_claim(confidence=0.95, evidence_chunk_ids=["c1", "c2"])
        rc_bad = _relation_claim(
            claim_id="rc-bad",
            confidence=0.5,
            source_entity_id="material:nmc",
            target_entity_id="mechanism:dendrite",
        )
        mat = GraphMaterializer()
        g = mat.build_graph_from_facts([], [rc_good, rc_bad])

        assert g.has_edge("material:lfp", "mechanism:sei")
        assert not g.has_edge("material:nmc", "mechanism:dendrite")


# ---------------------------------------------------------------------------
# Tests: deterministic output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    def test_same_input_same_graph(self) -> None:
        claims_e = [
            _entity_claim(claim_id="ec-b", entity_id="material:nmc", property_value="NMC"),
            _entity_claim(claim_id="ec-a", entity_id="material:lfp", property_value="LiFePO4"),
        ]
        claims_r = [
            _relation_claim(claim_id="rc-2", source_entity_id="material:nmc", target_entity_id="mechanism:dendrite"),
            _relation_claim(claim_id="rc-1", source_entity_id="material:lfp", target_entity_id="mechanism:sei"),
        ]
        mat = GraphMaterializer()
        g1 = mat.build_graph_from_claims(claims_e, claims_r)
        g2 = mat.build_graph_from_claims(claims_e, claims_r)

        assert sorted(g1.nodes) == sorted(g2.nodes)
        assert sorted(g1.edges(keys=True)) == sorted(g2.edges(keys=True))
        for node in g1.nodes:
            assert dict(g1.nodes[node]) == dict(g2.nodes[node])

    def test_order_independent(self) -> None:
        """Reversed input order still produces the same graph."""
        claims_e = [
            _entity_claim(claim_id="ec-a", entity_id="material:lfp"),
            _entity_claim(claim_id="ec-b", entity_id="material:nmc", property_value="NMC"),
        ]
        claims_e_reversed = list(reversed(claims_e))
        mat = GraphMaterializer()
        g1 = mat.build_graph_from_claims(claims_e, [])
        g2 = mat.build_graph_from_claims(claims_e_reversed, [])

        assert sorted(g1.nodes) == sorted(g2.nodes)
        for node in g1.nodes:
            assert dict(g1.nodes[node]) == dict(g2.nodes[node])


# ---------------------------------------------------------------------------
# Tests: ClaimCollection convenience
# ---------------------------------------------------------------------------


class TestBuildFromCollection:
    def test_collection_all_claims(self) -> None:
        coll = ClaimCollection(
            source_doc_id="papers/sample-001",
            entity_claims=[_entity_claim()],
            relation_claims=[_relation_claim()],
        )
        mat = GraphMaterializer()
        g = mat.build_graph_from_collection(coll)

        assert g.number_of_nodes() >= 1
        assert g.number_of_edges() == 1

    def test_collection_facts_only(self) -> None:
        ec_low = _entity_claim(claim_id="ec-low", confidence=0.5)
        ec_high = _entity_claim(claim_id="ec-high", confidence=0.95, entity_id="material:nmc")
        coll = ClaimCollection(
            source_doc_id="papers/sample-001",
            entity_claims=[ec_low, ec_high],
        )
        mat = GraphMaterializer()
        g = mat.build_graph_from_collection(coll, facts_only=True)

        assert not g.has_node("material:lfp")
        assert g.has_node("material:nmc")


# ---------------------------------------------------------------------------
# Tests: alias normalization
# ---------------------------------------------------------------------------


class TestAliasNormalization:
    def test_alias_map_collapses_entities(self) -> None:
        alias_map = {"lithium iron phosphate": "material:lfp"}
        ec = _entity_claim(entity_id="lithium iron phosphate")
        mat = GraphMaterializer(alias_map=alias_map)
        g = mat.build_graph_from_claims([ec], [])

        assert g.has_node("material:lfp")
        assert not g.has_node("lithium iron phosphate")

    def test_alias_map_normalizes_relation_endpoints(self) -> None:
        alias_map = {
            "lithium iron phosphate": "material:lfp",
            "sei layer": "mechanism:sei",
        }
        rc = _relation_claim(
            source_entity_id="lithium iron phosphate",
            target_entity_id="sei layer",
        )
        mat = GraphMaterializer(alias_map=alias_map)
        g = mat.build_graph_from_claims([], [rc])

        assert g.has_edge("material:lfp", "mechanism:sei")


# ---------------------------------------------------------------------------
# Tests: materialized graph matches expected structure
# ---------------------------------------------------------------------------


class TestExpectedStructure:
    def test_full_pipeline_structure(self) -> None:
        """End-to-end: entity claims + relation claims produce expected graph."""
        entities = [
            _entity_claim(claim_id="ec-1", entity_id="material:lfp", property_name="formula", property_value="LiFePO4"),
            _entity_claim(claim_id="ec-2", entity_id="mechanism:sei", entity_type=EntityType.FAILURE_MECHANISM, property_name="description", property_value="SEI growth"),
            _entity_claim(claim_id="ec-3", entity_id="test:cycling", entity_type=EntityType.TEST_CONDITION, property_name="type", property_value="galvanostatic"),
        ]
        relations = [
            _relation_claim(claim_id="rc-1", source_entity_id="material:lfp", target_entity_id="mechanism:sei", relation_type=RelationType.CAUSES),
            _relation_claim(claim_id="rc-2", source_entity_id="test:cycling", target_entity_id="material:lfp", relation_type=RelationType.TESTED_UNDER),
        ]
        mat = GraphMaterializer()
        g = mat.build_graph_from_claims(entities, relations)

        # 3 entity nodes
        assert g.number_of_nodes() == 3
        # 2 relation edges
        assert g.number_of_edges() == 2

        # Check node types
        assert g.nodes["material:lfp"]["entity_type"] == "Material"
        assert g.nodes["mechanism:sei"]["entity_type"] == "FailureMechanism"
        assert g.nodes["test:cycling"]["entity_type"] == "TestCondition"

        # Check edges
        assert g.has_edge("material:lfp", "mechanism:sei")
        assert g.has_edge("test:cycling", "material:lfp")

    def test_confidence_and_evidence_preserved(self) -> None:
        ec = _entity_claim(confidence=0.87, evidence_chunk_ids=["c3", "c1", "c2"])
        mat = GraphMaterializer()
        g = mat.build_graph_from_claims([ec], [])

        node = g.nodes["material:lfp"]
        assert node["confidence"] == 0.87
        # Evidence chunk IDs should be sorted
        assert node["evidence_chunk_ids"] == "c1,c2,c3"
