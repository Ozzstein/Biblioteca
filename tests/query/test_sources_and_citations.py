from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from llm_rag.config import Settings
from llm_rag.query.agent import (
    Citation,
    CitationType,
    EvidenceHit,
    GraphExpansion,
    QueryAgent,
    QueryContextBundle,
    WikiHit,
    _build_context_bundle,
    _build_synthesis_prompt,
    _classify_source,
    _format_context,
    _parse_citations,
    _parse_result,
    _strip_citation_markers,
    retrieve_evidence,
    retrieve_graph,
    retrieve_wiki,
)

# ---------------------------------------------------------------------------
# Citation model
# ---------------------------------------------------------------------------


class TestCitation:
    def test_valid_citation(self) -> None:
        c = Citation(
            source_doc_id="papers/lfp-001",
            chunk_id="3",
            quote="LFP shows 170 mAh/g",
            confidence=0.92,
        )
        assert c.source_doc_id == "papers/lfp-001"
        assert c.chunk_id == "3"
        assert c.confidence == 0.92

    def test_citation_optional_chunk(self) -> None:
        c = Citation(
            source_doc_id="papers/lfp-001",
            quote="LFP is stable",
            confidence=0.8,
        )
        assert c.chunk_id is None

    def test_citation_rejects_empty_doc_id(self) -> None:
        with pytest.raises(ValidationError):
            Citation(source_doc_id="", quote="text", confidence=0.5)

    def test_citation_rejects_out_of_range_confidence(self) -> None:
        with pytest.raises(ValidationError):
            Citation(
                source_doc_id="papers/x",
                quote="text",
                confidence=1.5,
            )


# ---------------------------------------------------------------------------
# EvidenceHit, WikiHit, GraphExpansion models
# ---------------------------------------------------------------------------


class TestHitModels:
    def test_evidence_hit(self) -> None:
        h = EvidenceHit(document_id="papers/lfp-001", chunk_id="3", score=0.95)
        assert h.document_id == "papers/lfp-001"
        assert h.snippet == ""

    def test_wiki_hit(self) -> None:
        h = WikiHit(page_path="wiki/materials/lfp.md", section="evidence")
        assert h.page_path == "wiki/materials/lfp.md"
        assert h.section == "evidence"

    def test_graph_expansion(self) -> None:
        g = GraphExpansion(
            entity_id="material:lfp",
            relation_type="USES_MATERIAL",
            connected_ids=["experiment:batch-a-001"],
        )
        assert g.entity_id == "material:lfp"
        assert len(g.connected_ids) == 1

    def test_evidence_hit_rejects_empty_doc_id(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceHit(document_id="", chunk_id="0", score=0.5)


# ---------------------------------------------------------------------------
# QueryContextBundle
# ---------------------------------------------------------------------------


class TestQueryContextBundle:
    def test_empty_bundle(self) -> None:
        bundle = QueryContextBundle()
        assert bundle.total_hits == 0
        assert bundle.is_empty is True
        assert bundle.evidence_hits == []
        assert bundle.wiki_hits == []
        assert bundle.graph_expansions == []
        assert bundle.citations == []

    def test_total_hits_counts_all_layers(self) -> None:
        bundle = QueryContextBundle(
            evidence_hits=[
                EvidenceHit(document_id="papers/a", chunk_id="1", score=0.9),
                EvidenceHit(document_id="papers/b", chunk_id="2", score=0.8),
            ],
            wiki_hits=[
                WikiHit(page_path="wiki/materials/lfp.md"),
            ],
            graph_expansions=[
                GraphExpansion(entity_id="material:lfp"),
            ],
        )
        assert bundle.total_hits == 4
        assert bundle.is_empty is False

    def test_bundle_with_citations(self) -> None:
        bundle = QueryContextBundle(
            evidence_hits=[
                EvidenceHit(document_id="papers/lfp-001", chunk_id="3", score=0.95),
            ],
            citations=[
                Citation(
                    source_doc_id="papers/lfp-001",
                    chunk_id="3",
                    quote="LFP shows 170 mAh/g",
                    confidence=0.92,
                ),
            ],
        )
        assert len(bundle.citations) == 1
        assert bundle.citations[0].source_doc_id == "papers/lfp-001"

    def test_bundle_serialization_roundtrip(self) -> None:
        bundle = QueryContextBundle(
            evidence_hits=[
                EvidenceHit(document_id="papers/a", chunk_id="1", score=0.9),
            ],
            wiki_hits=[
                WikiHit(page_path="wiki/materials/lfp.md", section="evidence"),
            ],
            graph_expansions=[
                GraphExpansion(
                    entity_id="material:lfp",
                    connected_ids=["experiment:batch-a-001"],
                ),
            ],
            citations=[
                Citation(
                    source_doc_id="papers/a",
                    chunk_id="1",
                    quote="capacity fade",
                    confidence=0.85,
                ),
            ],
        )
        data = bundle.model_dump()
        restored = QueryContextBundle.model_validate(data)
        assert restored.total_hits == bundle.total_hits
        assert restored.citations[0].quote == "capacity fade"


# ---------------------------------------------------------------------------
# Source classification helpers
# ---------------------------------------------------------------------------


class TestClassifySource:
    def test_wiki_source(self) -> None:
        hit = _classify_source("wiki/materials/lfp.md §evidence")
        assert isinstance(hit, WikiHit)
        assert hit.page_path == "wiki/materials/lfp.md"
        assert hit.section == "evidence"

    def test_wiki_source_no_section(self) -> None:
        hit = _classify_source("wiki/mechanisms/sei.md")
        assert isinstance(hit, WikiHit)
        assert hit.section == ""

    def test_paper_with_chunk(self) -> None:
        hit = _classify_source("papers/lfp-001 (chunk 3)")
        assert isinstance(hit, EvidenceHit)
        assert hit.document_id == "papers/lfp-001"
        assert hit.chunk_id == "3"

    def test_paper_without_chunk(self) -> None:
        hit = _classify_source("papers/lfp-002")
        assert isinstance(hit, EvidenceHit)
        assert hit.document_id == "papers/lfp-002"

    def test_unrecognized_source(self) -> None:
        hit = _classify_source("some-other-thing")
        assert hit is None


class TestBuildContextBundle:
    def test_mixed_sources(self) -> None:
        sources = [
            "wiki/materials/lfp.md §evidence",
            "papers/lfp-001 (chunk 2)",
            "papers/lfp-002 (chunk 5)",
        ]
        bundle = _build_context_bundle(sources)
        assert len(bundle.wiki_hits) == 1
        assert len(bundle.evidence_hits) == 2
        assert len(bundle.graph_expansions) == 0

    def test_empty_sources(self) -> None:
        bundle = _build_context_bundle([])
        assert bundle.is_empty is True


# ---------------------------------------------------------------------------
# _parse_result populates context_bundle
# ---------------------------------------------------------------------------


class TestParseResultBundle:
    def test_parse_result_builds_bundle(self) -> None:
        raw = (
            "LFP capacity fade is well documented.\n\n"
            "## Sources\n"
            "- wiki/materials/lfp.md §evidence\n"
            "- papers/lfp-001 (chunk 3)\n"
        )
        result = _parse_result(raw)
        assert result.context_bundle.total_hits == 2
        assert len(result.context_bundle.wiki_hits) == 1
        assert len(result.context_bundle.evidence_hits) == 1

    def test_parse_result_no_sources_empty_bundle(self) -> None:
        result = _parse_result("Plain answer with no sources.")
        assert result.context_bundle.is_empty is True


# ---------------------------------------------------------------------------
# QueryAgent.ask populates context_bundle
# ---------------------------------------------------------------------------


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        ANTHROPIC_API_KEY="test-key",
        root_dir=tmp_path,
        model_query_synthesis="claude-sonnet-4-6",
    )


async def test_ask_populates_context_bundle(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    raw_response = "SEI growth is the primary cause."
    evidence_hits = [
        EvidenceHit(document_id="papers/lfp-001", chunk_id="2", score=1.0, snippet="SEI growth"),
    ]
    wiki_hits = [
        WikiHit(page_path="wiki/mechanisms/sei.md", section="evidence", snippet="SEI layer"),
    ]
    with (
        patch("llm_rag.query.agent.run_agent", new_callable=AsyncMock) as mock_run,
        patch("llm_rag.query.agent.retrieve_evidence", new_callable=AsyncMock) as mock_ev,
        patch("llm_rag.query.agent.retrieve_wiki", new_callable=AsyncMock) as mock_wiki,
        patch("llm_rag.query.agent.retrieve_graph", new_callable=AsyncMock) as mock_graph,
    ):
        mock_run.return_value = raw_response
        mock_ev.return_value = evidence_hits
        mock_wiki.return_value = wiki_hits
        mock_graph.return_value = []
        agent = QueryAgent(settings=settings)
        result = await agent.ask("What causes LFP capacity fade?", MagicMock())

    assert not result.context_bundle.is_empty
    assert len(result.context_bundle.wiki_hits) == 1
    assert result.context_bundle.wiki_hits[0].section == "evidence"
    assert len(result.context_bundle.evidence_hits) == 1
    assert result.context_bundle.evidence_hits[0].document_id == "papers/lfp-001"


# ---------------------------------------------------------------------------
# Phased retrieval — retrieve_evidence
# ---------------------------------------------------------------------------


class TestRetrieveEvidence:
    async def test_returns_hits_from_search_chunks(self) -> None:
        mock_results = [
            {"doc_id": "papers/lfp-001", "chunk_index": 3, "text": "LFP capacity fade", "section": ""},
            {"doc_id": "papers/nmc-002", "chunk_index": 1, "text": "NMC degradation", "section": ""},
        ]
        with patch("llm_rag.mcp.corpus_io.search_chunks", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_results
            hits = await retrieve_evidence("capacity fade")
        assert len(hits) == 2
        assert hits[0].document_id == "papers/lfp-001"
        assert hits[0].chunk_id == "3"
        assert hits[0].snippet == "LFP capacity fade"
        assert hits[1].document_id == "papers/nmc-002"

    async def test_skips_entries_without_doc_id(self) -> None:
        mock_results = [
            {"doc_id": "", "chunk_index": 0, "text": "orphan"},
            {"doc_id": "papers/ok", "chunk_index": 0, "text": "valid"},
        ]
        with patch("llm_rag.mcp.corpus_io.search_chunks", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_results
            hits = await retrieve_evidence("test")
        assert len(hits) == 1
        assert hits[0].document_id == "papers/ok"

    async def test_returns_empty_on_exception(self) -> None:
        with patch("llm_rag.mcp.corpus_io.search_chunks", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = RuntimeError("chroma unavailable")
            hits = await retrieve_evidence("anything")
        assert hits == []


# ---------------------------------------------------------------------------
# Phased retrieval — retrieve_wiki
# ---------------------------------------------------------------------------


class TestRetrieveWiki:
    async def test_matches_pages_by_query_terms(self) -> None:
        with (
            patch("llm_rag.mcp.wiki_io.list_pages", new_callable=AsyncMock) as mock_list,
            patch("llm_rag.mcp.wiki_io.read_page", new_callable=AsyncMock) as mock_read,
        ):
            mock_list.return_value = [
                "materials/lfp.md",
                "materials/nmc.md",
                "mechanisms/sei.md",
            ]
            mock_read.return_value = "LFP is a cathode material..."
            hits = await retrieve_wiki("LFP degradation")
        assert len(hits) == 1
        assert hits[0].page_path == "materials/lfp.md"
        assert hits[0].snippet.startswith("LFP is a cathode")

    async def test_returns_empty_when_no_pages_match(self) -> None:
        with patch("llm_rag.mcp.wiki_io.list_pages", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = ["materials/nmc.md"]
            hits = await retrieve_wiki("LFP degradation")
        assert hits == []

    async def test_returns_empty_on_exception(self) -> None:
        with patch("llm_rag.mcp.wiki_io.list_pages", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = FileNotFoundError("wiki dir missing")
            hits = await retrieve_wiki("anything")
        assert hits == []

    async def test_handles_read_page_failure(self) -> None:
        with (
            patch("llm_rag.mcp.wiki_io.list_pages", new_callable=AsyncMock) as mock_list,
            patch("llm_rag.mcp.wiki_io.read_page", new_callable=AsyncMock) as mock_read,
        ):
            mock_list.return_value = ["materials/lfp.md"]
            mock_read.side_effect = FileNotFoundError("page missing")
            hits = await retrieve_wiki("LFP degradation")
        assert len(hits) == 1
        assert hits[0].snippet == ""


# ---------------------------------------------------------------------------
# Phased retrieval — retrieve_graph
# ---------------------------------------------------------------------------


class TestRetrieveGraph:
    async def test_expands_matching_entities(self) -> None:
        with (
            patch("llm_rag.mcp.graph_io.list_entities", new_callable=AsyncMock) as mock_list,
            patch("llm_rag.mcp.graph_io.get_neighbors", new_callable=AsyncMock) as mock_nbrs,
        ):
            mock_list.return_value = [
                {"entity_id": "material:lfp", "entity_type": "Material"},
                {"entity_id": "material:nmc", "entity_type": "Material"},
            ]
            mock_nbrs.return_value = ["experiment:batch-a-001"]
            expansions = await retrieve_graph("LFP capacity")
        assert len(expansions) == 1
        assert expansions[0].entity_id == "material:lfp"
        assert expansions[0].connected_ids == ["experiment:batch-a-001"]

    async def test_returns_empty_when_no_entities_match(self) -> None:
        with patch("llm_rag.mcp.graph_io.list_entities", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [{"entity_id": "material:nmc"}]
            expansions = await retrieve_graph("LFP capacity")
        assert expansions == []

    async def test_returns_empty_on_exception(self) -> None:
        with patch("llm_rag.mcp.graph_io.list_entities", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = RuntimeError("graph unavailable")
            expansions = await retrieve_graph("anything")
        assert expansions == []

    async def test_handles_neighbor_failure_gracefully(self) -> None:
        with (
            patch("llm_rag.mcp.graph_io.list_entities", new_callable=AsyncMock) as mock_list,
            patch("llm_rag.mcp.graph_io.get_neighbors", new_callable=AsyncMock) as mock_nbrs,
        ):
            mock_list.return_value = [{"entity_id": "material:lfp"}]
            mock_nbrs.side_effect = RuntimeError("traversal error")
            expansions = await retrieve_graph("LFP capacity")
        assert len(expansions) == 1
        assert expansions[0].connected_ids == []


# ---------------------------------------------------------------------------
# _format_context
# ---------------------------------------------------------------------------


class TestFormatContext:
    def test_formats_all_layers(self) -> None:
        bundle = QueryContextBundle(
            evidence_hits=[
                EvidenceHit(document_id="papers/a", chunk_id="1", score=0.9, snippet="some text"),
            ],
            wiki_hits=[
                WikiHit(page_path="materials/lfp.md", section="evidence", snippet="wiki text"),
            ],
            graph_expansions=[
                GraphExpansion(entity_id="material:lfp", connected_ids=["experiment:batch-a"]),
            ],
        )
        text = _format_context(bundle)
        assert "## Evidence Chunks" in text
        assert "papers/a chunk 1" in text
        assert "## Wiki Pages" in text
        assert "materials/lfp.md §evidence" in text
        assert "## Graph Entities" in text
        assert "material:lfp" in text

    def test_empty_bundle_shows_fallback(self) -> None:
        text = _format_context(QueryContextBundle())
        assert "No retrieval results found" in text


# ---------------------------------------------------------------------------
# QueryAgent.ask phased integration
# ---------------------------------------------------------------------------


async def test_ask_phased_all_layers_populated(tmp_path: Path) -> None:
    """Verify ask() calls all three retrieval phases and passes context to synthesis."""
    settings = _make_settings(tmp_path)
    evidence = [EvidenceHit(document_id="papers/a", chunk_id="0", score=1.0, snippet="ev")]
    wiki = [WikiHit(page_path="materials/lfp.md", snippet="wk")]
    graph = [GraphExpansion(entity_id="material:lfp", connected_ids=["x"])]

    with (
        patch("llm_rag.query.agent.run_agent", new_callable=AsyncMock) as mock_run,
        patch("llm_rag.query.agent.retrieve_evidence", new_callable=AsyncMock) as mock_ev,
        patch("llm_rag.query.agent.retrieve_wiki", new_callable=AsyncMock) as mock_wiki,
        patch("llm_rag.query.agent.retrieve_graph", new_callable=AsyncMock) as mock_graph,
    ):
        mock_ev.return_value = evidence
        mock_wiki.return_value = wiki
        mock_graph.return_value = graph
        mock_run.return_value = "Synthesized answer."

        agent = QueryAgent(settings=settings)
        result = await agent.ask("LFP fade", MagicMock())

    # All three retrieval phases called
    mock_ev.assert_awaited_once_with("LFP fade")
    mock_wiki.assert_awaited_once_with("LFP fade")
    mock_graph.assert_awaited_once_with("LFP fade")

    # Bundle populated from actual retrieval, not text parsing
    assert result.context_bundle.total_hits == 3
    assert len(result.context_bundle.evidence_hits) == 1
    assert len(result.context_bundle.wiki_hits) == 1
    assert len(result.context_bundle.graph_expansions) == 1

    # Synthesis prompt includes context
    prompt_arg = mock_run.call_args[0][1]
    assert "Evidence Chunks" in prompt_arg
    assert "papers/a" in prompt_arg


async def test_ask_phased_handles_all_empty(tmp_path: Path) -> None:
    """When all retrieval phases return nothing, ask() still produces an answer."""
    settings = _make_settings(tmp_path)
    with (
        patch("llm_rag.query.agent.run_agent", new_callable=AsyncMock) as mock_run,
        patch("llm_rag.query.agent.retrieve_evidence", new_callable=AsyncMock) as mock_ev,
        patch("llm_rag.query.agent.retrieve_wiki", new_callable=AsyncMock) as mock_wiki,
        patch("llm_rag.query.agent.retrieve_graph", new_callable=AsyncMock) as mock_graph,
    ):
        mock_ev.return_value = []
        mock_wiki.return_value = []
        mock_graph.return_value = []
        mock_run.return_value = "I don't have enough context."

        agent = QueryAgent(settings=settings)
        result = await agent.ask("unknown query", MagicMock())

    assert result.context_bundle.is_empty
    assert result.answer == "I don't have enough context."
    # Synthesis prompt should include the fallback message
    prompt_arg = mock_run.call_args[0][1]
    assert "No retrieval results found" in prompt_arg


# ---------------------------------------------------------------------------
# Citation type enum
# ---------------------------------------------------------------------------


class TestCitationType:
    def test_enum_values(self) -> None:
        assert CitationType.EVIDENCE.value == "evidence"
        assert CitationType.WIKI.value == "wiki"
        assert CitationType.GRAPH.value == "graph"

    def test_citation_with_type(self) -> None:
        c = Citation(
            source_doc_id="papers/lfp-001",
            chunk_id="3",
            quote="LFP shows 170 mAh/g",
            confidence=0.92,
            citation_type=CitationType.EVIDENCE,
        )
        assert c.citation_type == CitationType.EVIDENCE

    def test_citation_default_type(self) -> None:
        c = Citation(
            source_doc_id="papers/lfp-001",
            quote="some claim",
            confidence=0.8,
        )
        assert c.citation_type == CitationType.EVIDENCE


# ---------------------------------------------------------------------------
# _parse_citations — inline marker extraction
# ---------------------------------------------------------------------------


class TestParseCitations:
    def test_evidence_marker(self) -> None:
        text = "LFP shows 170 mAh/g [EVIDENCE:papers/lfp-001:3] at room temperature."
        citations = _parse_citations(text)
        assert len(citations) == 1
        assert citations[0].citation_type == CitationType.EVIDENCE
        assert citations[0].source_doc_id == "papers/lfp-001"
        assert citations[0].chunk_id == "3"

    def test_wiki_marker(self) -> None:
        text = "SEI growth is well understood [WIKI:wiki/mechanisms/sei.md] in the literature."
        citations = _parse_citations(text)
        assert len(citations) == 1
        assert citations[0].citation_type == CitationType.WIKI
        assert citations[0].source_doc_id == "wiki/mechanisms/sei.md"
        assert citations[0].chunk_id is None

    def test_graph_marker(self) -> None:
        text = "LFP is related to SEI formation [GRAPH:material:lfp] through cycling."
        citations = _parse_citations(text)
        assert len(citations) == 1
        assert citations[0].citation_type == CitationType.GRAPH
        assert citations[0].source_doc_id == "material:lfp"

    def test_multiple_markers(self) -> None:
        text = (
            "LFP capacity is 170 mAh/g [EVIDENCE:papers/lfp-001:3]. "
            "The wiki confirms this [WIKI:wiki/materials/lfp.md]. "
            "Graph shows connections [GRAPH:material:lfp]."
        )
        citations = _parse_citations(text)
        assert len(citations) == 3
        types = {c.citation_type for c in citations}
        assert types == {CitationType.EVIDENCE, CitationType.WIKI, CitationType.GRAPH}

    def test_deduplicates_same_marker(self) -> None:
        text = (
            "Claim A [EVIDENCE:papers/lfp-001:3]. "
            "Claim B also [EVIDENCE:papers/lfp-001:3]."
        )
        citations = _parse_citations(text)
        assert len(citations) == 1

    def test_no_markers(self) -> None:
        text = "Plain text with no citations."
        citations = _parse_citations(text)
        assert citations == []

    def test_quote_captures_surrounding_text(self) -> None:
        text = "LFP shows 170 mAh/g [EVIDENCE:papers/lfp-001:3] at room temperature."
        citations = _parse_citations(text)
        assert "170 mAh/g" in citations[0].quote
        assert "room temperature" in citations[0].quote


# ---------------------------------------------------------------------------
# _strip_citation_markers
# ---------------------------------------------------------------------------


class TestStripCitationMarkers:
    def test_strips_all_marker_types(self) -> None:
        text = (
            "Claim [EVIDENCE:papers/a:1] and [WIKI:wiki/b.md] "
            "and [GRAPH:material:c]."
        )
        clean = _strip_citation_markers(text)
        assert "[EVIDENCE:" not in clean
        assert "[WIKI:" not in clean
        assert "[GRAPH:" not in clean
        assert "Claim" in clean

    def test_no_markers_unchanged(self) -> None:
        text = "Plain text."
        assert _strip_citation_markers(text) == text


# ---------------------------------------------------------------------------
# _parse_result with citation markers
# ---------------------------------------------------------------------------


class TestParseResultCitations:
    def test_extracts_citations_from_answer(self) -> None:
        raw = (
            "## Direct Evidence\n"
            "LFP capacity is 170 mAh/g [EVIDENCE:papers/lfp-001:3].\n\n"
            "## Wiki Synthesis\n"
            "SEI growth is documented [WIKI:wiki/mechanisms/sei.md].\n\n"
            "## Graph Inferences\n"
            "LFP connects to SEI [GRAPH:material:lfp].\n\n"
            "## Sources\n"
            "- papers/lfp-001 (chunk 3)\n"
        )
        result = _parse_result(raw)
        assert len(result.context_bundle.citations) == 3
        ev = [c for c in result.context_bundle.citations if c.citation_type == CitationType.EVIDENCE]
        wiki = [c for c in result.context_bundle.citations if c.citation_type == CitationType.WIKI]
        graph = [c for c in result.context_bundle.citations if c.citation_type == CitationType.GRAPH]
        assert len(ev) == 1
        assert len(wiki) == 1
        assert len(graph) == 1
        assert ev[0].source_doc_id == "papers/lfp-001"
        assert ev[0].chunk_id == "3"

    def test_no_markers_no_citations(self) -> None:
        result = _parse_result("Plain answer with no markers.")
        assert result.context_bundle.citations == []


# ---------------------------------------------------------------------------
# _build_synthesis_prompt
# ---------------------------------------------------------------------------


class TestBuildSynthesisPrompt:
    def test_includes_citation_instructions(self) -> None:
        prompt = _build_synthesis_prompt("## Evidence Chunks\n- [papers/a chunk 1] text", "test query")
        assert "[EVIDENCE:doc_id:chunk_id]" in prompt
        assert "[WIKI:page_path]" in prompt
        assert "[GRAPH:entity_id]" in prompt
        assert "Direct Evidence" in prompt
        assert "Wiki Synthesis" in prompt
        assert "Graph Inferences" in prompt
        assert "test query" in prompt

    def test_includes_context(self) -> None:
        prompt = _build_synthesis_prompt("my context block", "a question")
        assert "my context block" in prompt
        assert "a question" in prompt


# ---------------------------------------------------------------------------
# QueryAgent.ask populates citations from synthesis output
# ---------------------------------------------------------------------------


async def test_ask_populates_citations_from_markers(tmp_path: Path) -> None:
    """Verify ask() parses citation markers from the synthesis output."""
    settings = _make_settings(tmp_path)
    evidence = [EvidenceHit(document_id="papers/lfp-001", chunk_id="3", score=1.0, snippet="capacity")]
    wiki = [WikiHit(page_path="wiki/mechanisms/sei.md", snippet="SEI")]
    graph = [GraphExpansion(entity_id="material:lfp", connected_ids=["experiment:batch-a"])]

    raw_response = (
        "## Direct Evidence\n"
        "LFP capacity is 170 mAh/g [EVIDENCE:papers/lfp-001:3].\n\n"
        "## Wiki Synthesis\n"
        "SEI growth is documented [WIKI:wiki/mechanisms/sei.md].\n\n"
        "## Graph Inferences\n"
        "LFP connects to SEI [GRAPH:material:lfp]."
    )

    with (
        patch("llm_rag.query.agent.run_agent", new_callable=AsyncMock) as mock_run,
        patch("llm_rag.query.agent.retrieve_evidence", new_callable=AsyncMock) as mock_ev,
        patch("llm_rag.query.agent.retrieve_wiki", new_callable=AsyncMock) as mock_wiki,
        patch("llm_rag.query.agent.retrieve_graph", new_callable=AsyncMock) as mock_graph,
    ):
        mock_run.return_value = raw_response
        mock_ev.return_value = evidence
        mock_wiki.return_value = wiki
        mock_graph.return_value = graph

        agent = QueryAgent(settings=settings)
        result = await agent.ask("LFP capacity fade", MagicMock())

    # Retrieval results preserved
    assert len(result.context_bundle.evidence_hits) == 1
    assert len(result.context_bundle.wiki_hits) == 1
    assert len(result.context_bundle.graph_expansions) == 1

    # Citations parsed from markers
    assert len(result.context_bundle.citations) == 3
    types = {c.citation_type for c in result.context_bundle.citations}
    assert types == {CitationType.EVIDENCE, CitationType.WIKI, CitationType.GRAPH}

    # Synthesis prompt included citation instructions
    prompt_arg = mock_run.call_args[0][1]
    assert "[EVIDENCE:doc_id:chunk_id]" in prompt_arg
