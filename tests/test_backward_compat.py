"""Backward-compatibility tests.

Ensures that existing CLI commands, MCP tool signatures, and QueryAgent
interfaces continue to work after v2 internals are introduced.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import networkx as nx
import pytest
from typer.testing import CliRunner

from llm_rag.cli import app
from llm_rag.query.agent import (
    Citation,
    CitationType,
    EvidenceHit,
    GraphExpansion,
    QueryAgent,
    QueryContextBundle,
    QueryResult,
    WikiHit,
    _parse_result,
)

runner = CliRunner()


# ── CLI backward compatibility ──────────────────────────────────────────


class TestCLICommandsExist:
    """All documented CLI commands must remain accessible."""

    def test_status_command(self) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    def test_ingest_help(self) -> None:
        result = runner.invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0
        # Legacy options must still appear
        assert "--path" in result.output
        assert "--doc-id" in result.output
        assert "--force" in result.output

    def test_pipeline_run_help(self) -> None:
        result = runner.invoke(app, ["pipeline", "run", "--help"])
        assert result.exit_code == 0
        assert "--path" in result.output
        assert "--force" in result.output

    def test_ask_help(self) -> None:
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0
        assert "--mode" in result.output
        assert "--quality" in result.output
        assert "--verbose" in result.output

    def test_build_graph_alias(self) -> None:
        result = runner.invoke(app, ["build-graph", "--help"])
        assert result.exit_code == 0

    def test_compile_wiki_alias(self) -> None:
        result = runner.invoke(app, ["compile-wiki", "--help"])
        assert result.exit_code == 0

    def test_materialize_graph_help(self) -> None:
        result = runner.invoke(app, ["materialize", "graph", "--help"])
        assert result.exit_code == 0
        assert "--input" in result.output
        assert "--output" in result.output
        assert "--force" in result.output

    def test_materialize_wiki_help(self) -> None:
        result = runner.invoke(app, ["materialize", "wiki", "--help"])
        assert result.exit_code == 0

    def test_materialize_all_help(self) -> None:
        result = runner.invoke(app, ["materialize", "all", "--help"])
        assert result.exit_code == 0


class TestCLIFlows:
    """Old CLI flows produce the expected output structure."""

    def test_status_output_sections(self) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Battery Research OS" in result.output
        assert "API Keys:" in result.output
        assert "Models:" in result.output
        assert "Pipeline:" in result.output
        assert "Corpus:" in result.output

    @patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
    def test_ingest_default_path(self, mock_run: AsyncMock) -> None:
        result = runner.invoke(app, ["ingest"])
        assert result.exit_code == 0
        assert "Ingesting" in result.output
        call_path = mock_run.call_args[0][0]
        assert str(call_path).endswith("raw/inbox")

    @patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
    def test_pipeline_run_default(self, mock_run: AsyncMock) -> None:
        result = runner.invoke(app, ["pipeline", "run"])
        assert result.exit_code == 0
        assert "Running pipeline" in result.output

    @patch("llm_rag.cli.asyncio.run")
    def test_ask_positional_question(self, mock_asyncio_run: MagicMock) -> None:
        mock_asyncio_run.return_value = QueryResult(answer="test", sources=[])
        result = runner.invoke(app, ["ask", "my question"])
        assert result.exit_code == 0

    @patch("llm_rag.query.planner.QueryPlanner.ask", new_callable=AsyncMock)
    @patch("llm_rag.mcp.pool.MCPPool.__aexit__", new_callable=AsyncMock)
    @patch("llm_rag.mcp.pool.MCPPool.__aenter__", new_callable=AsyncMock)
    def test_ask_with_mode_option(
        self, mock_enter: AsyncMock, mock_exit: AsyncMock, mock_ask: AsyncMock
    ) -> None:
        mock_enter.return_value = MagicMock()
        mock_ask.return_value = QueryResult(answer="answer", sources=[])
        result = runner.invoke(app, ["ask", "question", "--mode", "wiki"])
        assert result.exit_code == 0


# ── QueryAgent backward compatibility ──────────────────────────────────


class TestQueryAgentInterface:
    """QueryAgent.ask() signature and return type must remain stable."""

    def test_query_agent_init_accepts_optional_settings(self) -> None:
        sig = inspect.signature(QueryAgent.__init__)
        params = list(sig.parameters.keys())
        assert "settings" in params
        assert sig.parameters["settings"].default is None

    def test_ask_signature(self) -> None:
        sig = inspect.signature(QueryAgent.ask)
        params = list(sig.parameters.keys())
        assert params == ["self", "query", "pool"]

    def test_query_result_fields(self) -> None:
        qr = QueryResult(answer="test")
        assert hasattr(qr, "answer")
        assert hasattr(qr, "sources")
        assert hasattr(qr, "context_bundle")
        assert isinstance(qr.sources, list)
        assert isinstance(qr.context_bundle, QueryContextBundle)

    def test_query_context_bundle_fields(self) -> None:
        bundle = QueryContextBundle()
        assert hasattr(bundle, "evidence_hits")
        assert hasattr(bundle, "wiki_hits")
        assert hasattr(bundle, "graph_expansions")
        assert hasattr(bundle, "citations")
        assert bundle.total_hits == 0
        assert bundle.is_empty is True

    def test_evidence_hit_fields(self) -> None:
        hit = EvidenceHit(document_id="doc1", chunk_id="0", score=0.9, snippet="text")
        assert hit.document_id == "doc1"
        assert hit.chunk_id == "0"
        assert hit.score == 0.9

    def test_wiki_hit_fields(self) -> None:
        hit = WikiHit(page_path="materials/lfp.md", section="evidence", snippet="x")
        assert hit.page_path == "materials/lfp.md"

    def test_graph_expansion_fields(self) -> None:
        exp = GraphExpansion(entity_id="material:lfp", connected_ids=["mechanism:sei"])
        assert exp.entity_id == "material:lfp"

    def test_citation_fields(self) -> None:
        c = Citation(
            source_doc_id="papers/test",
            quote="quote",
            confidence=0.9,
            citation_type=CitationType.EVIDENCE,
        )
        assert c.source_doc_id == "papers/test"
        assert c.citation_type == CitationType.EVIDENCE

    def test_parse_result_legacy_format(self) -> None:
        raw = (
            "Answer text.\n\n"
            "## Sources\n"
            "- wiki/materials/lfp.md §evidence\n"
            "- papers/lfp-001 (chunk 3)\n"
        )
        result = _parse_result(raw)
        assert result.answer == "Answer text."
        assert len(result.sources) == 2
        assert result.context_bundle.wiki_hits
        assert result.context_bundle.evidence_hits

    async def test_ask_returns_query_result(self, tmp_path: Path) -> None:
        from llm_rag.config import Settings

        settings = Settings(
            ANTHROPIC_API_KEY="test-key",
            root_dir=tmp_path,
            model_query_synthesis="claude-sonnet-4-6",
        )
        raw = "Answer.\n\n## Sources\n- papers/test (chunk 1)"
        with (
            patch("llm_rag.query.agent.run_agent", new_callable=AsyncMock, return_value=raw),
            patch("llm_rag.query.agent.retrieve_evidence", new_callable=AsyncMock, return_value=[]),
            patch("llm_rag.query.agent.retrieve_wiki", new_callable=AsyncMock, return_value=[]),
            patch("llm_rag.query.agent.retrieve_graph", new_callable=AsyncMock, return_value=[]),
        ):
            agent = QueryAgent(settings=settings)
            result = await agent.ask("test query", MagicMock())
        assert isinstance(result, QueryResult)
        assert isinstance(result.context_bundle, QueryContextBundle)


# ── MCP graph_io backward compatibility ─────────────────────────────────


@pytest.fixture()
def graph_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings

    get_settings.cache_clear()

    snapshots = tmp_path / "graph" / "snapshots"
    snapshots.mkdir(parents=True)
    (tmp_path / "graph" / "exports").mkdir(parents=True)
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "entity-normalization.yaml").write_text(
        "materials:\n"
        "  LFP:\n"
        "    entity_id: 'material:lfp'\n"
        "    aliases:\n"
        "      - LiFePO4\n"
    )

    g: nx.MultiDiGraph = nx.MultiDiGraph()
    g.add_node("material:lfp", entity_type="Material", canonical_name="LFP")
    g.add_node("mechanism:sei", entity_type="FailureMechanism", canonical_name="SEI")
    g.add_edge("mechanism:sei", "material:lfp", key="r1", relation_type="AFFECTS")
    nx.write_graphml(g, str(snapshots / "latest.graphml"))

    yield tmp_path

    get_settings.cache_clear()


class TestGraphMCPBackwardCompat:
    """MCP graph tools must accept the same parameters and return the same shapes."""

    async def test_get_entity_signature(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import get_entity

        sig = inspect.signature(get_entity)
        assert list(sig.parameters.keys()) == ["entity_id"]

    async def test_get_entity_returns_dict_with_entity_id(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import get_entity

        result = await get_entity("material:lfp")
        assert isinstance(result, dict)
        assert result["entity_id"] == "material:lfp"

    async def test_get_entity_returns_none_for_missing(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import get_entity

        result = await get_entity("no:such")
        assert result is None

    async def test_list_entities_default_returns_all(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import list_entities

        result = await list_entities()
        assert isinstance(result, list)
        assert len(result) >= 2
        assert all("entity_id" in e for e in result)

    async def test_list_entities_with_type_filter(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import list_entities

        result = await list_entities("Material")
        assert all(e["entity_type"] == "Material" for e in result)

    async def test_get_neighbors_signature(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import get_neighbors

        sig = inspect.signature(get_neighbors)
        params = sig.parameters
        assert "entity_id" in params
        assert "depth" in params
        assert params["depth"].default == 1

    async def test_get_neighbors_returns_list(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import get_neighbors

        result = await get_neighbors("mechanism:sei")
        assert isinstance(result, list)
        assert "material:lfp" in result

    async def test_get_canonical_resolves_alias(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import get_canonical

        result = await get_canonical("LiFePO4")
        assert result == "material:lfp"

    async def test_get_canonical_returns_none_for_unknown(self, graph_env: Path) -> None:
        from llm_rag.mcp.graph_io import get_canonical

        result = await get_canonical("unknown-alias")
        assert result is None

    async def test_merge_extraction_signature(self) -> None:
        from llm_rag.mcp.graph_io import merge_extraction

        sig = inspect.signature(merge_extraction)
        assert list(sig.parameters.keys()) == ["export_path"]

    async def test_merge_by_doc_id_signature(self) -> None:
        from llm_rag.mcp.graph_io import merge_by_doc_id

        sig = inspect.signature(merge_by_doc_id)
        assert list(sig.parameters.keys()) == ["doc_id"]

    async def test_materialize_from_claims_signature(self) -> None:
        from llm_rag.mcp.graph_io import materialize_from_claims

        sig = inspect.signature(materialize_from_claims)
        assert list(sig.parameters.keys()) == ["claims_json"]


# ── MCP wiki_io backward compatibility ──────────────────────────────────


@pytest.fixture()
def wiki_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings

    get_settings.cache_clear()

    wiki = tmp_path / "wiki" / "materials"
    wiki.mkdir(parents=True)
    (wiki / "lfp.md").write_text(
        "# LFP\n"
        "<!-- auto-start: evidence -->\nold\n<!-- auto-end: evidence -->\n"
        "<!-- human-start: notes -->\nmy notes\n<!-- human-end: notes -->\n"
    )

    templates = tmp_path / "config" / "page-templates"
    templates.mkdir(parents=True)
    (templates / "material.md").write_text("# {{ canonical_name }}\n{{ entity_id }}")
    (templates / "_fallback.md").write_text("# {{ canonical_name }}")

    yield tmp_path

    get_settings.cache_clear()


class TestWikiMCPBackwardCompat:
    """MCP wiki tools must accept old-style inputs."""

    async def test_read_page_signature(self) -> None:
        from llm_rag.mcp.wiki_io import read_page

        sig = inspect.signature(read_page)
        assert list(sig.parameters.keys()) == ["relative_path"]

    async def test_read_page_returns_string(self, wiki_env: Path) -> None:
        from llm_rag.mcp.wiki_io import read_page

        result = await read_page("materials/lfp.md")
        assert isinstance(result, str)
        assert "LFP" in result

    async def test_list_pages_signature(self) -> None:
        from llm_rag.mcp.wiki_io import list_pages

        sig = inspect.signature(list_pages)
        assert "subdir" in sig.parameters
        assert sig.parameters["subdir"].default == ""

    async def test_list_pages_returns_relative_paths(self, wiki_env: Path) -> None:
        from llm_rag.mcp.wiki_io import list_pages

        result = await list_pages("materials")
        assert isinstance(result, list)
        assert "materials/lfp.md" in result

    async def test_get_template_signature(self) -> None:
        from llm_rag.mcp.wiki_io import get_template

        sig = inspect.signature(get_template)
        assert list(sig.parameters.keys()) == ["page_type"]

    async def test_get_template_returns_content(self, wiki_env: Path) -> None:
        from llm_rag.mcp.wiki_io import get_template

        result = await get_template("material")
        assert "canonical_name" in result

    async def test_get_template_fallback(self, wiki_env: Path) -> None:
        from llm_rag.mcp.wiki_io import get_template

        result = await get_template("nonexistent-type")
        assert isinstance(result, str)

    async def test_write_auto_sections_signature(self) -> None:
        from llm_rag.mcp.wiki_io import write_auto_sections

        sig = inspect.signature(write_auto_sections)
        params = list(sig.parameters.keys())
        assert "relative_path" in params
        assert "sections" in params

    async def test_write_auto_sections_old_style(self, wiki_env: Path) -> None:
        from llm_rag.mcp.wiki_io import write_auto_sections

        await write_auto_sections("materials/lfp.md", {"evidence": "| new | data |"})
        content = (wiki_env / "wiki" / "materials" / "lfp.md").read_text()
        assert "new | data" in content
        assert "my notes" in content  # human section preserved

    async def test_create_page_signature(self) -> None:
        from llm_rag.mcp.wiki_io import create_page

        sig = inspect.signature(create_page)
        params = list(sig.parameters.keys())
        assert "relative_path" in params
        assert "page_type" in params
        assert "substitutions" in params

    async def test_create_page_old_style(self, wiki_env: Path) -> None:
        from llm_rag.mcp.wiki_io import create_page

        await create_page(
            "materials/new.md",
            "material",
            {"canonical_name": "NewMat", "entity_id": "material:new"},
        )
        created = wiki_env / "wiki" / "materials" / "new.md"
        assert created.exists()
        assert "NewMat" in created.read_text()

    async def test_write_provenance_signature(self) -> None:
        from llm_rag.mcp.wiki_io import write_provenance

        sig = inspect.signature(write_provenance)
        params = list(sig.parameters.keys())
        assert "relative_path" in params
        assert "provenance" in params

    async def test_materialize_page_signature(self) -> None:
        from llm_rag.mcp.wiki_io import materialize_page

        sig = inspect.signature(materialize_page)
        params = list(sig.parameters.keys())
        assert "entity_id" in params
        assert "entity_type" in params
        assert "canonical_name" in params
        assert "relative_path" in params
        assert "claims_json" in params
        assert "evidence_json" in params


# ── Validation models backward compat ───────────────────────────────────


class TestValidationModelsBackwardCompat:
    """Pydantic validation models used by MCP tools must accept old-format inputs."""

    def test_provenance_entry_old_fields(self) -> None:
        from llm_rag.mcp.wiki_io import ProvenanceEntry

        entry = ProvenanceEntry(
            source_doc_id="papers/test-001",
            chunk_id="3",
            confidence=0.85,
            extracted_at="2026-04-18",
        )
        assert entry.source_doc_id == "papers/test-001"

    def test_provenance_entry_optional_chunk_id(self) -> None:
        from llm_rag.mcp.wiki_io import ProvenanceEntry

        entry = ProvenanceEntry(
            source_doc_id="papers/test",
            confidence=0.5,
            extracted_at="2026-04-18",
        )
        assert entry.chunk_id == ""

    def test_wiki_sections_input_accepts_dict(self) -> None:
        from llm_rag.mcp.wiki_io import WikiSectionsInput

        inp = WikiSectionsInput(sections={"evidence": "content"})
        assert inp.sections["evidence"] == "content"

    def test_wiki_create_page_input_coerces_substitutions(self) -> None:
        from llm_rag.mcp.wiki_io import WikiCreatePageInput

        inp = WikiCreatePageInput(
            relative_path="materials/test.md",
            page_type="material",
            substitutions={"key": "value"},
        )
        assert inp.substitutions["key"] == "value"
