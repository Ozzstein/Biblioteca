from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from llm_rag.mcp.graph_io import (
    get_canonical,
    get_entity,
    get_neighbors,
    list_entities,
    merge_by_doc_id,
)


@pytest.fixture()
def graph_snapshot(tmp_path: Path) -> Path:
    snapshots = tmp_path / "graph" / "snapshots"
    snapshots.mkdir(parents=True)
    g: nx.MultiDiGraph = nx.MultiDiGraph()
    g.add_node("material:lfp", entity_type="Material", canonical_name="LFP")
    g.add_node("mechanism:sei", entity_type="FailureMechanism", canonical_name="SEI")
    g.add_node("project:alpha", entity_type="Project", canonical_name="Alpha")
    g.add_edge("mechanism:sei", "material:lfp", key="rel-001", relation_type="AFFECTS", weight=1.0)
    g.add_edge("material:lfp", "project:alpha", key="rel-002", relation_type="ASSOCIATED_WITH", weight=1.0)
    snapshot = snapshots / "latest.graphml"
    nx.write_graphml(g, str(snapshot))
    return tmp_path


@pytest.fixture()
def norm_yaml(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    (config / "entity-normalization.yaml").write_text(
        "materials:\n"
        "  LFP:\n"
        "    entity_id: 'material:lfp'\n"
        "    aliases:\n"
        "      - LiFePO4\n"
        "      - lithium iron phosphate\n"
    )
    return tmp_path


async def test_get_entity_returns_node_data(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await get_entity("material:lfp")
    assert result is not None
    assert result["entity_id"] == "material:lfp"
    assert result["canonical_name"] == "LFP"
    get_settings.cache_clear()


async def test_get_entity_returns_none_for_missing(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await get_entity("material:no-such")
    assert result is None
    get_settings.cache_clear()


async def test_list_entities_returns_all(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await list_entities()
    ids = [e["entity_id"] for e in result]
    assert "material:lfp" in ids
    assert "mechanism:sei" in ids
    get_settings.cache_clear()


async def test_list_entities_filtered_by_type(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await list_entities("Material")
    assert all(e["entity_type"] == "Material" for e in result)
    get_settings.cache_clear()


async def test_get_neighbors_returns_adjacent(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await get_neighbors("mechanism:sei")
    assert "material:lfp" in result
    get_settings.cache_clear()


async def test_get_neighbors_depth_2(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await get_neighbors("mechanism:sei", depth=2)
    assert "material:lfp" in result
    assert "project:alpha" in result
    get_settings.cache_clear()


async def test_get_canonical_resolves_alias(norm_yaml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(norm_yaml))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await get_canonical("LiFePO4")
    assert result == "material:lfp"
    get_settings.cache_clear()


async def test_get_canonical_returns_none_for_unknown(norm_yaml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(norm_yaml))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await get_canonical("no-such-alias")
    assert result is None
    get_settings.cache_clear()


async def test_merge_by_doc_id_delegates_to_merge_logic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    # Create the normalized export file
    exports = tmp_path / "graph" / "exports"
    exports.mkdir(parents=True)
    (tmp_path / "graph" / "snapshots").mkdir(parents=True)
    data = {"doc_id": "papers/test-001", "entities": [], "relations": []}
    (exports / "papers-test-001.json").write_text(json.dumps(data))
    merge_calls: list[Path] = []

    def fake_run_merge(path: Path) -> None:
        merge_calls.append(path)

    monkeypatch.setattr("llm_rag.mcp.graph_io._run_merge", fake_run_merge)
    await merge_by_doc_id("papers/test-001")
    assert len(merge_calls) == 1
    assert merge_calls[0] == exports / "papers-test-001.json"
    get_settings.cache_clear()


# --- Tests for canonical ID rewriting in merge ---


def _make_extraction_json(
    entities: list[dict[str, object]],
    relations: list[dict[str, object]],
) -> str:
    """Build a minimal ExtractionResult JSON string."""
    data = {
        "doc_id": "papers/alias-test",
        "entities": entities,
        "relations": relations,
        "chunks_processed": 1,
        "extraction_model": "test",
        "extracted_at": "2026-04-24T00:00:00Z",
    }
    return json.dumps(data)


@pytest.fixture()
def merge_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up tmp dirs + normalization yaml for merge tests."""
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()

    (tmp_path / "graph" / "snapshots").mkdir(parents=True)
    (tmp_path / "graph" / "exports").mkdir(parents=True)
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "entity-normalization.yaml").write_text(
        "materials:\n"
        "  LFP:\n"
        "    entity_id: 'material:lfp'\n"
        "    aliases:\n"
        "      - LiFePO4\n"
        "      - lithium iron phosphate\n"
        "  NMC811:\n"
        "    entity_id: 'material:nmc811'\n"
        "    aliases:\n"
        "      - NMC 811\n"
        "      - NCM811\n"
    )
    return tmp_path


def test_merge_rewrites_relation_endpoints_to_canonical(merge_env: Path) -> None:
    """Relations whose source/target use aliases should be rewritten to canonical IDs."""
    from llm_rag.mcp.graph_io import _run_merge

    exports = merge_env / "graph" / "exports"
    export_json = _make_extraction_json(
        entities=[
            {"entity_id": "material:lifepo4", "entity_type": "Material",
             "canonical_name": "LiFePO4", "aliases": ["LiFePO4"]},
            {"entity_id": "material:nmc811", "entity_type": "Material",
             "canonical_name": "NMC811", "aliases": []},
        ],
        relations=[
            {"relation_id": "rel-1", "relation_type": "AFFECTS",
             "source_entity_id": "material:lifepo4",
             "target_entity_id": "material:nmc811", "weight": 1.0},
        ],
    )
    path = exports / "alias-test.json"
    path.write_text(export_json)
    _run_merge(path)

    import networkx as nx
    snapshot = merge_env / "graph" / "snapshots" / "latest.graphml"
    g = nx.read_graphml(str(snapshot), force_multigraph=True)

    # The alias "lifepo4" should have resolved to canonical "material:lfp"
    assert g.has_node("material:lfp")
    assert not g.has_node("material:lifepo4")
    # Edge should connect canonical IDs
    edges = list(g.edges(data=True, keys=True))
    rel = [e for e in edges if e[2] == "rel-1"]
    assert len(rel) == 1
    assert rel[0][0] == "material:lfp"
    assert rel[0][1] == "material:nmc811"

    from llm_rag.config import get_settings
    get_settings.cache_clear()


def test_merge_deduplicates_entities_with_same_canonical_id(merge_env: Path) -> None:
    """Two entities that alias-resolve to the same canonical ID should produce one node."""
    from llm_rag.mcp.graph_io import _run_merge

    exports = merge_env / "graph" / "exports"
    export_json = _make_extraction_json(
        entities=[
            {"entity_id": "material:lifepo4", "entity_type": "Material",
             "canonical_name": "LiFePO4", "aliases": []},
            {"entity_id": "material:lithium-iron-phosphate", "entity_type": "Material",
             "canonical_name": "lithium iron phosphate", "aliases": []},
        ],
        relations=[],
    )
    path = exports / "dedup-test.json"
    path.write_text(export_json)
    _run_merge(path)

    import networkx as nx
    snapshot = merge_env / "graph" / "snapshots" / "latest.graphml"
    g = nx.read_graphml(str(snapshot), force_multigraph=True)

    # Both should collapse to material:lfp — only one node
    assert g.has_node("material:lfp")
    assert g.number_of_nodes() == 1

    from llm_rag.config import get_settings
    get_settings.cache_clear()


def test_merge_preserves_unaliased_entities(merge_env: Path) -> None:
    """Entities with no alias match should keep their original ID."""
    from llm_rag.mcp.graph_io import _run_merge

    exports = merge_env / "graph" / "exports"
    export_json = _make_extraction_json(
        entities=[
            {"entity_id": "process:new-process", "entity_type": "Process",
             "canonical_name": "New Process", "aliases": []},
        ],
        relations=[],
    )
    path = exports / "noalias-test.json"
    path.write_text(export_json)
    _run_merge(path)

    import networkx as nx
    snapshot = merge_env / "graph" / "snapshots" / "latest.graphml"
    g = nx.read_graphml(str(snapshot), force_multigraph=True)
    assert g.has_node("process:new-process")

    from llm_rag.config import get_settings
    get_settings.cache_clear()


def test_merge_relation_with_both_endpoints_aliased(merge_env: Path) -> None:
    """Both source and target are aliases — both should resolve to canonical IDs."""
    from llm_rag.mcp.graph_io import _run_merge

    exports = merge_env / "graph" / "exports"
    export_json = _make_extraction_json(
        entities=[
            {"entity_id": "material:lifepo4", "entity_type": "Material",
             "canonical_name": "LiFePO4", "aliases": []},
            {"entity_id": "material:ncm811", "entity_type": "Material",
             "canonical_name": "NCM811", "aliases": []},
        ],
        relations=[
            {"relation_id": "rel-both", "relation_type": "ASSOCIATED_WITH",
             "source_entity_id": "material:lifepo4",
             "target_entity_id": "material:ncm811", "weight": 0.8},
        ],
    )
    path = exports / "both-alias-test.json"
    path.write_text(export_json)
    _run_merge(path)

    import networkx as nx
    snapshot = merge_env / "graph" / "snapshots" / "latest.graphml"
    g = nx.read_graphml(str(snapshot), force_multigraph=True)

    edges = list(g.edges(data=True, keys=True))
    rel = [e for e in edges if e[2] == "rel-both"]
    assert len(rel) == 1
    assert rel[0][0] == "material:lfp"
    assert rel[0][1] == "material:nmc811"

    from llm_rag.config import get_settings
    get_settings.cache_clear()
