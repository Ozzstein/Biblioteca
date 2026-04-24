from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.config import Settings
from llm_rag.research.coordinator import CandidateDocument, ResearchAgent


def test_candidate_document_content_key_with_doi():
    c = CandidateDocument(
        title="LFP Degradation",
        abstract="Abstract text.",
        source="arxiv",
        doi="10.1016/j.example.2024.001",
    )
    assert c.content_key == "doi:10.1016/j.example.2024.001"


def test_candidate_document_content_key_doi_lowercased():
    c1 = CandidateDocument(title="T", abstract="A", source="arxiv", doi="10.1016/J.EXAMPLE")
    c2 = CandidateDocument(title="T", abstract="A", source="arxiv", doi="10.1016/j.example")
    assert c1.content_key == c2.content_key


def test_candidate_document_content_key_without_doi_uses_title_hash():
    c = CandidateDocument(title="LFP Degradation", abstract="Abstract.", source="arxiv")
    assert c.content_key.startswith("title:")
    assert len(c.content_key) == len("title:") + 16


def test_candidate_document_content_key_title_hash_case_insensitive():
    c1 = CandidateDocument(title="LFP DEGRADATION", abstract="A", source="arxiv")
    c2 = CandidateDocument(title="lfp degradation", abstract="A", source="arxiv")
    assert c1.content_key == c2.content_key


def test_candidate_document_defaults():
    c = CandidateDocument(title="T", abstract="A", source="arxiv")
    assert c.doi is None
    assert c.arxiv_id is None
    assert c.pdf_url is None
    assert c.source_url is None
    assert c.published_year is None
    assert c.authors == []
    assert c.relevance_score == 0.0


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        root_dir=tmp_path,
        relevance_threshold=0.6,
        model_relevance_scoring="claude-haiku-4-5-20251001",
    )


def _make_candidate(doi: str | None = None, title: str = "LFP Paper") -> CandidateDocument:
    return CandidateDocument(
        title=title,
        abstract="Study of LFP degradation mechanisms.",
        source="arxiv",
        doi=doi,
        pdf_url="https://arxiv.org/pdf/2301.00001",
    )


def _mock_pool() -> tuple[MagicMock, MagicMock]:
    """Return (mock_pool_cls, mock_pool_instance) with async context manager wired up."""
    mock_pool_instance = MagicMock()
    mock_pool_cls = MagicMock()
    mock_pool_cls.return_value.__aenter__ = AsyncMock(return_value=mock_pool_instance)
    mock_pool_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_pool_cls, mock_pool_instance


async def test_research_agent_deduplicates_by_doi(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c1 = _make_candidate(doi="10.1016/same")
    c2 = _make_candidate(doi="10.1016/same")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c1, c2])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4", "pdf"))

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.9})
        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert len(written) == 1
    mock_subagent.fetch.assert_called_once()


async def test_research_agent_filters_low_relevance(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c = _make_candidate(doi="10.1016/low")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4", "pdf"))

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.3})
        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert written == []
    mock_subagent.fetch.assert_not_called()


async def test_research_agent_writes_pdf_to_inbox(tmp_path: Path):
    settings = _make_settings(tmp_path)
    (tmp_path / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
    c = _make_candidate(doi="10.1016/good")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4 content", "pdf"))

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.85})
        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert len(written) == 1
    assert written[0].suffix == ".pdf"
    assert written[0].read_bytes() == b"%PDF-1.4 content"


async def test_research_agent_skips_fetch_none(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c = _make_candidate(doi="10.1016/nofetch")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c])
    mock_subagent.fetch = AsyncMock(return_value=None)

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.9})
        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert written == []


async def test_research_agent_subagent_search_exception_continues(tmp_path: Path):
    settings = _make_settings(tmp_path)

    failing_subagent = AsyncMock()
    failing_subagent.search = AsyncMock(side_effect=RuntimeError("network error"))

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock), \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        agent = ResearchAgent(settings=settings, subagents=[failing_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert written == []


async def test_research_agent_deduplicates_by_title_when_no_doi(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c1 = CandidateDocument(title="LFP Paper", abstract="Abstract.", source="arxiv")
    c2 = CandidateDocument(title="LFP PAPER", abstract="Abstract.", source="semantic_scholar")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c1, c2])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4", "pdf"))

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.9})
        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP"])

    assert len(written) == 1
