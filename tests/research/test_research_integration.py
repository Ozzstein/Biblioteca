from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.config import Settings
from llm_rag.research.coordinator import CandidateDocument, ResearchAgent
from llm_rag.research.subagents.arxiv import ArXivSubagent
from llm_rag.research.subagents.firecrawl import FirecrawlSubagent
from llm_rag.research.subagents.google_scholar import GoogleScholarSubagent
from llm_rag.research.subagents.openalex import OpenAlexSubagent
from llm_rag.research.subagents.pubmed import PubMedSubagent
from llm_rag.research.subagents.semantic_scholar import SemanticScholarSubagent
from llm_rag.research.subagents.unpaywall import UnpaywallSubagent


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        firecrawl_api_key="fc-test",
        serpapi_key="",
        root_dir=tmp_path,
        relevance_threshold=0.6,
        model_relevance_scoring="claude-haiku-4-5-20251001",
    )


async def test_research_agent_end_to_end_with_all_subagents(tmp_path: Path):
    """
    ArXiv returns one candidate (high relevance, PDF fetch succeeds).
    SemanticScholar returns same paper by DOI (deduplicated).
    OpenAlex returns one new candidate (low relevance, filtered out).
    PubMed, Unpaywall, Firecrawl, GoogleScholar return empty.
    """
    lfp_candidate = CandidateDocument(
        title="LFP Capacity Fade at High Temperatures",
        abstract="We study LFP fade mechanisms at elevated temperatures.",
        source="arxiv",
        doi="10.1016/j.xxx.2024.001",
        pdf_url="https://arxiv.org/pdf/2401.00001",
    )
    lfp_duplicate = CandidateDocument(
        title="LFP Capacity Fade at High Temperatures",
        abstract="We study LFP fade mechanisms at elevated temperatures.",
        source="semantic_scholar",
        doi="10.1016/j.xxx.2024.001",
        pdf_url="https://example.com/paper.pdf",
    )
    low_relevance = CandidateDocument(
        title="Polymer Chemistry Applications",
        abstract="Study of polymer applications in industrial settings.",
        source="openalex",
        doi="10.1016/j.polymer.2024",
        pdf_url="https://example.com/polymer.pdf",
    )

    mock_arxiv = AsyncMock(spec=ArXivSubagent)
    mock_arxiv.search = AsyncMock(return_value=[lfp_candidate])
    mock_arxiv.fetch = AsyncMock(return_value=(b"%PDF-1.4 lfp", "pdf"))

    mock_s2 = AsyncMock(spec=SemanticScholarSubagent)
    mock_s2.search = AsyncMock(return_value=[lfp_duplicate])
    mock_s2.fetch = AsyncMock(return_value=(b"%PDF-1.4 lfp-s2", "pdf"))

    mock_oa = AsyncMock(spec=OpenAlexSubagent)
    mock_oa.search = AsyncMock(return_value=[low_relevance])
    mock_oa.fetch = AsyncMock(return_value=(b"%PDF-1.4 polymer", "pdf"))

    mock_pubmed = AsyncMock(spec=PubMedSubagent)
    mock_pubmed.search = AsyncMock(return_value=[])
    mock_pubmed.fetch = AsyncMock(return_value=None)

    mock_unpaywall = AsyncMock(spec=UnpaywallSubagent)
    mock_unpaywall.search = AsyncMock(return_value=[])
    mock_unpaywall.fetch = AsyncMock(return_value=None)

    mock_firecrawl = AsyncMock(spec=FirecrawlSubagent)
    mock_firecrawl.search = AsyncMock(return_value=[])
    mock_firecrawl.fetch = AsyncMock(return_value=None)

    mock_gs = AsyncMock(spec=GoogleScholarSubagent)
    mock_gs.search = AsyncMock(return_value=[])
    mock_gs.fetch = AsyncMock(return_value=None)

    subagents = [mock_arxiv, mock_s2, mock_oa, mock_pubmed, mock_unpaywall, mock_firecrawl, mock_gs]
    scores = iter([0.9, 0.2])

    # Mock the MCPPool as an async context manager
    mock_pool_instance = MagicMock()
    mock_pool_cls = MagicMock()
    mock_pool_cls.return_value.__aenter__ = AsyncMock(return_value=mock_pool_instance)
    mock_pool_cls.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "llm_rag.research.coordinator.run_agent", new_callable=AsyncMock
    ) as mock_run_agent, patch(
        "llm_rag.research.coordinator.MCPPool", mock_pool_cls
    ):
        # Mock run_agent to return JSON scores
        async def _side_effect(*args: object, **kwargs: object) -> str:
            return json.dumps({"score": next(scores)})

        mock_run_agent.side_effect = _side_effect

        settings = _settings(tmp_path)
        agent = ResearchAgent(settings=settings, subagents=subagents)
        written = await agent.run(topics=["LFP degradation", "battery capacity fade"])

    # Only one file: duplicate deduplicated, low-relevance filtered
    assert len(written) == 1
    assert written[0].suffix == ".pdf"
    assert written[0].read_bytes() == b"%PDF-1.4 lfp"

    # Dedup: fetch called only once (on arxiv, first in list)
    mock_arxiv.fetch.assert_called_once()
    mock_s2.fetch.assert_not_called()
    mock_oa.fetch.assert_not_called()
