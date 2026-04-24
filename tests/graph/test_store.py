# tests/graph/test_store.py
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from llm_rag.graph.builder import merge_extraction_result
from llm_rag.graph.store import GraphStore
from llm_rag.schemas.entities import (
    Entity,
    EntityType,
    ExtractionResult,
    Material,
    Relation,
    RelationType,
)


@pytest.fixture
def store(tmp_path: Path) -> GraphStore:
    return GraphStore(snapshot_path=tmp_path / "graph.graphml")


def _make_material(entity_id: str, name: str) -> Material:
    return Material(entity_id=entity_id, canonical_name=name)


def _make_relation(rid: str, src: str, tgt: str, rtype: RelationType) -> Relation:
    return Relation(
        relation_id=rid,
        relation_type=rtype,
        source_entity_id=src,
        target_entity_id=tgt,
    )


def test_add_entity(store: GraphStore) -> None:
    store.add_entity(_make_material("material:lfp", "LFP"))
    assert store.has_node("material:lfp")
    assert store.node_count() == 1


def test_add_relation(store: GraphStore) -> None:
    store.add_entity(_make_material("material:lfp", "LFP"))
    store.add_entity(
        Entity(
            entity_id="mechanism:sei",
            entity_type=EntityType.FAILURE_MECHANISM,
            canonical_name="SEI Growth",
        )
    )
    store.add_relation(
        _make_relation("r1", "material:lfp", "mechanism:sei", RelationType.CAUSES)
    )
    assert store.edge_count() == 1


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "snap.graphml"
    s = GraphStore(snapshot_path=path)
    s.add_entity(_make_material("material:lfp", "LFP"))
    s.add_entity(_make_material("material:nmc", "NMC"))
    # Add two parallel edges between same pair to test MultiDiGraph preservation
    s.add_relation(
        _make_relation("r1", "material:lfp", "material:nmc", RelationType.ASSOCIATED_WITH)
    )
    s.add_relation(
        _make_relation("r2", "material:lfp", "material:nmc", RelationType.CAUSES)
    )
    s.save()

    # Load into new store and verify roundtrip integrity
    s2 = GraphStore(snapshot_path=path)
    s2.load()
    assert s2.has_node("material:lfp")
    assert s2.has_node("material:nmc")
    assert s2.node_count() == 2
    # Verify parallel edges survived roundtrip
    assert s2.edge_count() == 2
    # Verify the loaded graph is still a MultiDiGraph
    import networkx as nx
    assert isinstance(s2._g, nx.MultiDiGraph)


def test_neighbors(store: GraphStore) -> None:
    store.add_entity(_make_material("material:lfp", "LFP"))
    store.add_entity(_make_material("material:nmc", "NMC"))
    store.add_relation(
        _make_relation("r1", "material:lfp", "material:nmc", RelationType.ASSOCIATED_WITH)
    )
    assert "material:nmc" in store.neighbors("material:lfp")


def test_merge_extraction_result(store: GraphStore) -> None:
    result = ExtractionResult(
        doc_id="papers/test",
        entities=[_make_material("material:lfp", "LFP")],
        relations=[],
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(UTC),
    )
    merge_extraction_result(result, store)
    assert store.has_node("material:lfp")


def test_merge_multiple_results_accumulates(store: GraphStore) -> None:
    r1 = ExtractionResult(
        doc_id="doc1",
        entities=[_make_material("material:lfp", "LFP")],
        relations=[],
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(UTC),
    )
    r2 = ExtractionResult(
        doc_id="doc2",
        entities=[_make_material("material:nmc", "NMC")],
        relations=[],
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(UTC),
    )
    merge_extraction_result(r1, store)
    merge_extraction_result(r2, store)
    assert store.node_count() == 2


def test_load_nonexistent_file_is_noop(tmp_path: Path) -> None:
    """Test that loading a nonexistent file does not raise an exception."""
    path = tmp_path / "nonexistent" / "graph.graphml"
    store = GraphStore(snapshot_path=path)
    # Should not raise an exception
    store.load()
    # Graph should be empty after load attempt
    assert store.node_count() == 0
    assert store.edge_count() == 0
