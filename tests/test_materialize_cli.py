"""Tests for materialize / build-graph / compile-wiki CLI commands."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from llm_rag.cli import app
from llm_rag.evidence.models import (
    DocumentType,
    EvidenceChunk,
    EvidenceDocument,
    EvidenceStore,
    ProvenanceSpan,
)
from llm_rag.knowledge.models import (
    ClaimCollection,
    ClaimStatus,
    EntityClaim,
    RelationClaim,
)
from llm_rag.schemas.entities import EntityType, RelationType

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_entity_claim(
    entity_id: str = "material:lfp",
    entity_type: EntityType = EntityType.MATERIAL,
    prop_name: str = "capacity_mah_g",
    prop_value: str = "170",
    confidence: float = 0.92,
    doc_id: str = "papers/lfp-001",
) -> EntityClaim:
    return EntityClaim(
        claim_id=f"ec-{entity_id}-{prop_name}",
        statement=f"{entity_id} has {prop_name}={prop_value}",
        confidence=confidence,
        source_doc_id=doc_id,
        evidence_chunk_ids=[f"{doc_id}:chunk-001"],
        status=ClaimStatus.CANDIDATE,
        extracted_at=datetime(2026, 4, 18, tzinfo=UTC),
        entity_id=entity_id,
        entity_type=entity_type,
        property_name=prop_name,
        property_value=prop_value,
    )


def _make_relation_claim(
    source: str = "material:lfp",
    target: str = "mechanism:sei",
    rel_type: RelationType = RelationType.CAUSES,
    doc_id: str = "papers/lfp-001",
) -> RelationClaim:
    return RelationClaim(
        claim_id=f"rc-{source}-{target}",
        statement=f"{source} causes {target}",
        confidence=0.85,
        source_doc_id=doc_id,
        evidence_chunk_ids=[f"{doc_id}:chunk-002"],
        status=ClaimStatus.CANDIDATE,
        extracted_at=datetime(2026, 4, 18, tzinfo=UTC),
        source_entity_id=source,
        target_entity_id=target,
        relation_type=rel_type,
    )


def _make_collection(doc_id: str = "papers/lfp-001") -> ClaimCollection:
    return ClaimCollection(
        source_doc_id=doc_id,
        entity_claims=[_make_entity_claim(doc_id=doc_id)],
        relation_claims=[_make_relation_claim(doc_id=doc_id)],
        extracted_at=datetime(2026, 4, 18, tzinfo=UTC),
    )


def _make_evidence_store(doc_id: str = "papers/lfp-001") -> EvidenceStore:
    return EvidenceStore(
        document=EvidenceDocument(
            doc_id=doc_id,
            source_path=f"raw/{doc_id}.md",
            doc_type=DocumentType.PAPER,
            content_hash="sha256:abc123",
            title="LFP Capacity Fade",
            ingested_at=datetime(2026, 4, 18, tzinfo=UTC),
        ),
        chunks=[
            EvidenceChunk(
                chunk_id=f"{doc_id}:chunk-001",
                document_id=doc_id,
                text="LFP shows 170 mAh/g capacity.",
                content_hash=EvidenceChunk.hash_text("LFP shows 170 mAh/g capacity."),
                span=ProvenanceSpan(start_byte=0, end_byte=30),
                chunk_index=0,
                token_estimate=7,
            ),
            EvidenceChunk(
                chunk_id=f"{doc_id}:chunk-002",
                document_id=doc_id,
                text="SEI growth causes capacity fade.",
                content_hash=EvidenceChunk.hash_text("SEI growth causes capacity fade."),
                span=ProvenanceSpan(start_byte=30, end_byte=62),
                chunk_index=1,
                token_estimate=7,
            ),
        ],
    )


def _write_claims(tmp_dir: Path, doc_id: str = "papers/lfp-001") -> Path:
    """Write a ClaimCollection JSON file and return its path."""
    coll = _make_collection(doc_id)
    out = tmp_dir / f"{doc_id.replace('/', '-')}-claims.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(coll.model_dump_json(indent=2))
    return out


def _write_evidence(tmp_dir: Path, doc_id: str = "papers/lfp-001") -> Path:
    """Write an EvidenceStore JSON file and return its path."""
    store = _make_evidence_store(doc_id)
    out = tmp_dir / f"{doc_id.replace('/', '-')}-evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(store.model_dump_json(indent=2))
    return out


# ---------------------------------------------------------------------------
# Help / discovery tests
# ---------------------------------------------------------------------------


def test_materialize_help():
    result = runner.invoke(app, ["materialize", "--help"])
    assert result.exit_code == 0
    assert "graph" in result.output.lower()
    assert "wiki" in result.output.lower()
    assert "all" in result.output.lower()


def test_build_graph_help():
    result = runner.invoke(app, ["build-graph", "--help"])
    assert result.exit_code == 0
    assert "graph" in result.output.lower()


def test_compile_wiki_help():
    result = runner.invoke(app, ["compile-wiki", "--help"])
    assert result.exit_code == 0
    assert "wiki" in result.output.lower()


# ---------------------------------------------------------------------------
# Materialize graph tests
# ---------------------------------------------------------------------------


def test_materialize_graph_from_claims(tmp_path):
    """materialize graph reads claims and writes a graphml snapshot."""
    input_dir = tmp_path / "exports"
    input_dir.mkdir()
    _write_claims(input_dir)

    output_dir = tmp_path / "graph_out"
    output_dir.mkdir()

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = output_dir
        s.wiki_dir = tmp_path / "wiki"

        result = runner.invoke(app, [
            "materialize", "graph",
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ])

    assert result.exit_code == 0, result.output
    assert "Materializing graph" in result.output
    assert "nodes" in result.output
    snapshot = output_dir / "snapshots" / "latest.graphml"
    assert snapshot.exists()


def test_materialize_graph_refuses_without_force(tmp_path):
    """materialize graph refuses to overwrite existing snapshot without --force."""
    input_dir = tmp_path / "exports"
    input_dir.mkdir()
    _write_claims(input_dir)

    output_dir = tmp_path / "graph_out"
    snapshot = output_dir / "snapshots" / "latest.graphml"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("<graphml/>")

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = output_dir

        result = runner.invoke(app, [
            "materialize", "graph",
            "--input", str(input_dir),
            "--output", str(output_dir),
        ])

    assert result.exit_code == 1
    assert "Use --force" in result.output


def test_materialize_graph_empty_input(tmp_path):
    """materialize graph with no claims produces an empty graph."""
    input_dir = tmp_path / "exports"
    input_dir.mkdir()

    output_dir = tmp_path / "graph_out"
    output_dir.mkdir()

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = output_dir

        result = runner.invoke(app, [
            "materialize", "graph",
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ])

    assert result.exit_code == 0
    assert "0 nodes" in result.output


# ---------------------------------------------------------------------------
# Materialize wiki tests
# ---------------------------------------------------------------------------


def test_materialize_wiki_from_claims(tmp_path):
    """materialize wiki reads claims + evidence and writes wiki pages."""
    input_dir = tmp_path / "exports"
    input_dir.mkdir()
    _write_claims(input_dir)
    _write_evidence(input_dir)

    wiki_dir = tmp_path / "wiki_out"
    wiki_dir.mkdir()

    # Create a fallback template
    template_dir = tmp_path / "config" / "page-templates"
    template_dir.mkdir(parents=True)
    (template_dir / "_fallback.md").write_text(
        "# {{canonical_name}}\n\n"
        "## Properties\n<!-- auto-start: properties -->\n<!-- auto-end: properties -->\n\n"
        "## Linked Entities\n<!-- auto-start: linked-entities -->\n<!-- auto-end: linked-entities -->\n\n"
        "## Evidence\n<!-- auto-start: evidence -->\n<!-- auto-end: evidence -->\n\n"
        "## Contradictions\n<!-- auto-start: contradictions -->\n<!-- auto-end: contradictions -->\n\n"
        "## Provenance\n<!-- auto-start: provenance -->\n<!-- auto-end: provenance -->\n\n"
        "## Last Updated\n<!-- auto-start: last-updated -->\n<!-- auto-end: last-updated -->\n"
    )

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = tmp_path / "graph"
        s.wiki_dir = wiki_dir

        result = runner.invoke(app, [
            "materialize", "wiki",
            "--input", str(input_dir),
            "--output", str(wiki_dir),
            "--force",
        ])

    assert result.exit_code == 0, result.output
    assert "Materializing wiki" in result.output
    assert "pages" in result.output


def test_materialize_wiki_empty_input(tmp_path):
    """materialize wiki with no claims produces zero pages."""
    input_dir = tmp_path / "exports"
    input_dir.mkdir()

    wiki_dir = tmp_path / "wiki_out"
    wiki_dir.mkdir()

    template_dir = tmp_path / "config" / "page-templates"
    template_dir.mkdir(parents=True)

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = tmp_path / "graph"
        s.wiki_dir = wiki_dir

        result = runner.invoke(app, [
            "materialize", "wiki",
            "--input", str(input_dir),
            "--output", str(wiki_dir),
            "--force",
        ])

    assert result.exit_code == 0
    assert "0 pages" in result.output


# ---------------------------------------------------------------------------
# Materialize all tests
# ---------------------------------------------------------------------------


def test_materialize_all(tmp_path):
    """materialize all rebuilds both graph and wiki."""
    input_dir = tmp_path / "exports"
    input_dir.mkdir()
    _write_claims(input_dir)
    _write_evidence(input_dir)

    graph_dir = tmp_path / "graph_out"
    graph_dir.mkdir()
    wiki_dir = tmp_path / "wiki_out"
    wiki_dir.mkdir()

    template_dir = tmp_path / "config" / "page-templates"
    template_dir.mkdir(parents=True)
    (template_dir / "_fallback.md").write_text(
        "# {{canonical_name}}\n\n"
        "## Properties\n<!-- auto-start: properties -->\n<!-- auto-end: properties -->\n\n"
        "## Linked Entities\n<!-- auto-start: linked-entities -->\n<!-- auto-end: linked-entities -->\n\n"
        "## Evidence\n<!-- auto-start: evidence -->\n<!-- auto-end: evidence -->\n\n"
        "## Contradictions\n<!-- auto-start: contradictions -->\n<!-- auto-end: contradictions -->\n\n"
        "## Provenance\n<!-- auto-start: provenance -->\n<!-- auto-end: provenance -->\n\n"
        "## Last Updated\n<!-- auto-start: last-updated -->\n<!-- auto-end: last-updated -->\n"
    )

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = graph_dir
        s.wiki_dir = wiki_dir

        result = runner.invoke(app, [
            "materialize", "all",
            "--input", str(input_dir),
            "--force",
        ])

    assert result.exit_code == 0, result.output
    assert "Graph materialized" in result.output
    assert "Wiki materialized" in result.output
    assert "All surfaces materialized" in result.output

    snapshot = graph_dir / "snapshots" / "latest.graphml"
    assert snapshot.exists()


# ---------------------------------------------------------------------------
# Alias tests
# ---------------------------------------------------------------------------


def test_build_graph_alias(tmp_path):
    """build-graph is an alias for materialize graph."""
    input_dir = tmp_path / "exports"
    input_dir.mkdir()
    _write_claims(input_dir)

    output_dir = tmp_path / "graph_out"
    output_dir.mkdir()

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = output_dir

        result = runner.invoke(app, [
            "build-graph",
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ])

    assert result.exit_code == 0, result.output
    assert "nodes" in result.output
    snapshot = output_dir / "snapshots" / "latest.graphml"
    assert snapshot.exists()


def test_compile_wiki_alias(tmp_path):
    """compile-wiki is an alias for materialize wiki."""
    input_dir = tmp_path / "exports"
    input_dir.mkdir()

    wiki_dir = tmp_path / "wiki_out"
    wiki_dir.mkdir()

    template_dir = tmp_path / "config" / "page-templates"
    template_dir.mkdir(parents=True)

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = tmp_path / "graph"
        s.wiki_dir = wiki_dir

        result = runner.invoke(app, [
            "compile-wiki",
            "--input", str(input_dir),
            "--output", str(wiki_dir),
            "--force",
        ])

    assert result.exit_code == 0, result.output
    assert "pages" in result.output


# ---------------------------------------------------------------------------
# Integration: deterministic rebuild
# ---------------------------------------------------------------------------


def test_graph_rebuild_is_deterministic(tmp_path):
    """Two successive graph materializations from the same claims produce identical graphs."""
    import networkx as nx

    input_dir = tmp_path / "exports"
    input_dir.mkdir()
    _write_claims(input_dir)

    out1 = tmp_path / "graph1"
    out1.mkdir()
    out2 = tmp_path / "graph2"
    out2.mkdir()

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = out1

        result1 = runner.invoke(app, [
            "materialize", "graph",
            "--input", str(input_dir),
            "--output", str(out1),
            "--force",
        ])

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = out2

        result2 = runner.invoke(app, [
            "materialize", "graph",
            "--input", str(input_dir),
            "--output", str(out2),
            "--force",
        ])

    assert result1.exit_code == 0
    assert result2.exit_code == 0

    g1 = nx.read_graphml(str(out1 / "snapshots" / "latest.graphml"), force_multigraph=True)
    g2 = nx.read_graphml(str(out2 / "snapshots" / "latest.graphml"), force_multigraph=True)

    assert set(g1.nodes) == set(g2.nodes)
    assert set(g1.edges) == set(g2.edges)
    for node in g1.nodes:
        assert g1.nodes[node] == g2.nodes[node]


def test_multiple_collections_merged(tmp_path):
    """Graph materializer merges claims from multiple documents."""
    import networkx as nx

    input_dir = tmp_path / "exports"
    input_dir.mkdir()
    _write_claims(input_dir, doc_id="papers/lfp-001")

    # Second collection with a different entity
    coll2 = ClaimCollection(
        source_doc_id="papers/nmc-002",
        entity_claims=[
            _make_entity_claim(
                entity_id="material:nmc811",
                prop_name="capacity_mah_g",
                prop_value="200",
                doc_id="papers/nmc-002",
            )
        ],
        relation_claims=[],
        extracted_at=datetime(2026, 4, 18, tzinfo=UTC),
    )
    (input_dir / "nmc-002-claims.json").write_text(coll2.model_dump_json(indent=2))

    output_dir = tmp_path / "graph_out"
    output_dir.mkdir()

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.config_dir = tmp_path / "config"
        s.graph_dir = output_dir

        result = runner.invoke(app, [
            "materialize", "graph",
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ])

    assert result.exit_code == 0
    g = nx.read_graphml(str(output_dir / "snapshots" / "latest.graphml"), force_multigraph=True)
    assert g.has_node("material:lfp")
    assert g.has_node("material:nmc811")
