# tests/graph/test_provenance_persistence.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from llm_rag.graph.store import GraphStore
from llm_rag.schemas.entities import Entity, EntityType, Relation, RelationType
from llm_rag.schemas.provenance import ExtractionMethod, ProvenanceRecord


@pytest.fixture
def store(tmp_path: Path) -> GraphStore:
    return GraphStore(snapshot_path=tmp_path / "graph.graphml")


def _make_provenance(doc_id: str = "papers/lfp-001", confidence: float = 0.92) -> ProvenanceRecord:
    return ProvenanceRecord(
        source_doc_id=doc_id,
        source_path=f"raw/{doc_id}.md",
        section="§3.2",
        timestamp=datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC),
        confidence=confidence,
        extraction_method=ExtractionMethod.CLAUDE_HAIKU,
        extractor_model="claude-haiku-4-5-20251001",
    )


def _make_entity_with_provenance() -> Entity:
    return Entity(
        entity_id="material:lfp",
        entity_type=EntityType.MATERIAL,
        canonical_name="Lithium Iron Phosphate",
        aliases=["LFP", "LiFePO4", "lithium-iron-phosphate"],
        provenance=[
            _make_provenance("papers/lfp-001", 0.92),
            _make_provenance("papers/lfp-002", 0.85),
        ],
    )


class TestAliasesPersistence:
    """Aliases preserved in node attributes after save/load roundtrip."""

    def test_aliases_stored_on_node(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        attrs = store._g.nodes["material:lfp"]
        aliases = json.loads(attrs["aliases"])
        assert aliases == ["LFP", "LiFePO4", "lithium-iron-phosphate"]

    def test_aliases_survive_roundtrip(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        store.save()
        store2 = GraphStore(store.snapshot_path)
        store2.load()
        aliases = json.loads(store2._g.nodes["material:lfp"]["aliases"])
        assert aliases == ["LFP", "LiFePO4", "lithium-iron-phosphate"]

    def test_empty_aliases_stored_as_empty_list(self, store: GraphStore) -> None:
        entity = Entity(
            entity_id="material:nmc",
            entity_type=EntityType.MATERIAL,
            canonical_name="NMC",
            aliases=[],
        )
        store.add_entity(entity)
        aliases = json.loads(store._g.nodes["material:nmc"]["aliases"])
        assert aliases == []


class TestChunkIdsPersistence:
    """Supporting chunk IDs stored in node attributes."""

    def test_evidence_chunk_ids_stored(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity, evidence_chunk_ids=["chunk-001", "chunk-002", "chunk-003"])
        attrs = store._g.nodes["material:lfp"]
        chunk_ids = json.loads(attrs["evidence_chunk_ids"])
        assert chunk_ids == ["chunk-001", "chunk-002", "chunk-003"]

    def test_evidence_chunk_ids_roundtrip(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity, evidence_chunk_ids=["chunk-001", "chunk-002"])
        store.save()
        store2 = GraphStore(store.snapshot_path)
        store2.load()
        chunk_ids = json.loads(store2._g.nodes["material:lfp"]["evidence_chunk_ids"])
        assert chunk_ids == ["chunk-001", "chunk-002"]

    def test_no_chunk_ids_defaults_to_empty(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        chunk_ids = json.loads(store._g.nodes["material:lfp"]["evidence_chunk_ids"])
        assert chunk_ids == []


class TestSourceDocIdPersistence:
    """Source document IDs tracked in node attributes."""

    def test_source_doc_ids_from_provenance(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        attrs = store._g.nodes["material:lfp"]
        source_doc_ids = json.loads(attrs["source_doc_ids"])
        assert set(source_doc_ids) == {"papers/lfp-001", "papers/lfp-002"}

    def test_source_doc_ids_roundtrip(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        store.save()
        store2 = GraphStore(store.snapshot_path)
        store2.load()
        source_doc_ids = json.loads(store2._g.nodes["material:lfp"]["source_doc_ids"])
        assert set(source_doc_ids) == {"papers/lfp-001", "papers/lfp-002"}

    def test_no_provenance_yields_empty_source_doc_ids(self, store: GraphStore) -> None:
        entity = Entity(
            entity_id="material:nmc",
            entity_type=EntityType.MATERIAL,
            canonical_name="NMC",
        )
        store.add_entity(entity)
        source_doc_ids = json.loads(store._g.nodes["material:nmc"]["source_doc_ids"])
        assert source_doc_ids == []


class TestConfidencePersistence:
    """Confidence scores preserved in node attributes."""

    def test_confidence_stored_as_max(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()  # 0.92 and 0.85
        store.add_entity(entity)
        attrs = store._g.nodes["material:lfp"]
        assert float(attrs["confidence"]) == pytest.approx(0.92)

    def test_confidence_roundtrip(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        store.save()
        store2 = GraphStore(store.snapshot_path)
        store2.load()
        assert float(store2._g.nodes["material:lfp"]["confidence"]) == pytest.approx(0.92)

    def test_no_provenance_confidence_zero(self, store: GraphStore) -> None:
        entity = Entity(
            entity_id="material:nmc",
            entity_type=EntityType.MATERIAL,
            canonical_name="NMC",
        )
        store.add_entity(entity)
        assert float(store._g.nodes["material:nmc"]["confidence"]) == pytest.approx(0.0)


class TestTimestampPersistence:
    """Timestamps recorded in node attributes."""

    def test_created_at_stored(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        attrs = store._g.nodes["material:lfp"]
        assert "created_at" in attrs
        assert attrs["created_at"] == "2026-04-18T10:00:00+00:00"

    def test_updated_at_stored(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        attrs = store._g.nodes["material:lfp"]
        assert "updated_at" in attrs
        assert attrs["updated_at"] == "2026-04-18T10:00:00+00:00"

    def test_timestamps_roundtrip(self, store: GraphStore) -> None:
        entity = _make_entity_with_provenance()
        store.add_entity(entity)
        store.save()
        store2 = GraphStore(store.snapshot_path)
        store2.load()
        attrs = store2._g.nodes["material:lfp"]
        assert attrs["created_at"] == "2026-04-18T10:00:00+00:00"
        assert attrs["updated_at"] == "2026-04-18T10:00:00+00:00"

    def test_no_provenance_timestamps_empty(self, store: GraphStore) -> None:
        entity = Entity(
            entity_id="material:nmc",
            entity_type=EntityType.MATERIAL,
            canonical_name="NMC",
        )
        store.add_entity(entity)
        attrs = store._g.nodes["material:nmc"]
        assert attrs["created_at"] == ""
        assert attrs["updated_at"] == ""


class TestRelationProvenancePersistence:
    """Relation edges also carry provenance attributes."""

    def test_relation_source_doc_ids(self, store: GraphStore) -> None:
        entity_a = Entity(entity_id="material:lfp", entity_type=EntityType.MATERIAL, canonical_name="LFP")
        entity_b = Entity(entity_id="mechanism:sei", entity_type=EntityType.FAILURE_MECHANISM, canonical_name="SEI")
        store.add_entity(entity_a)
        store.add_entity(entity_b)
        rel = Relation(
            relation_id="rel-001",
            relation_type=RelationType.CAUSES,
            source_entity_id="material:lfp",
            target_entity_id="mechanism:sei",
            provenance=[_make_provenance("papers/lfp-001", 0.88)],
        )
        store.add_relation(rel)
        edge_data = store._g.edges["material:lfp", "mechanism:sei", "rel-001"]
        assert json.loads(edge_data["source_doc_ids"]) == ["papers/lfp-001"]
        assert float(edge_data["confidence"]) == pytest.approx(0.88)

    def test_relation_provenance_roundtrip(self, store: GraphStore) -> None:
        entity_a = Entity(entity_id="material:lfp", entity_type=EntityType.MATERIAL, canonical_name="LFP")
        entity_b = Entity(entity_id="mechanism:sei", entity_type=EntityType.FAILURE_MECHANISM, canonical_name="SEI")
        store.add_entity(entity_a)
        store.add_entity(entity_b)
        rel = Relation(
            relation_id="rel-001",
            relation_type=RelationType.CAUSES,
            source_entity_id="material:lfp",
            target_entity_id="mechanism:sei",
            provenance=[_make_provenance("papers/lfp-001", 0.88)],
        )
        store.add_relation(rel)
        store.save()
        store2 = GraphStore(store.snapshot_path)
        store2.load()
        edge_data = store2._g.edges["material:lfp", "mechanism:sei", "rel-001"]
        assert json.loads(edge_data["source_doc_ids"]) == ["papers/lfp-001"]
        assert float(edge_data["confidence"]) == pytest.approx(0.88)
