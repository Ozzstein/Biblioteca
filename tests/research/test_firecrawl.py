from __future__ import annotations

from unittest.mock import MagicMock, patch

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.firecrawl import FirecrawlSubagent


async def test_firecrawl_search_returns_empty():
    subagent = FirecrawlSubagent(api_key="test-key")
    results = await subagent.search(["LFP"])
    assert results == []


async def test_firecrawl_fetch_returns_markdown():
    candidate = CandidateDocument(
        title="LFP Web Page",
        abstract="Abstract.",
        source="firecrawl",
        source_url="https://example.com/lfp-paper",
    )

    mock_response = MagicMock()
    mock_response.markdown = "# LFP Paper\n\nAbstract content here."

    with patch("llm_rag.research.subagents.firecrawl.V1FirecrawlApp") as mock_cls:
        mock_app = MagicMock()
        mock_cls.return_value = mock_app
        mock_app.scrape_url.return_value = mock_response

        subagent = FirecrawlSubagent(api_key="test-key")
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "md"
    assert content == b"# LFP Paper\n\nAbstract content here."
    mock_app.scrape_url.assert_called_once_with(
        "https://example.com/lfp-paper", formats=["markdown"]
    )


async def test_firecrawl_fetch_returns_none_when_no_source_url():
    candidate = CandidateDocument(
        title="No URL", abstract="Abstract.", source="firecrawl", source_url=None
    )
    subagent = FirecrawlSubagent(api_key="test-key")
    result = await subagent.fetch(candidate)
    assert result is None


async def test_firecrawl_fetch_returns_none_when_markdown_empty():
    candidate = CandidateDocument(
        title="Empty Page",
        abstract="Abstract.",
        source="firecrawl",
        source_url="https://example.com/empty",
    )

    mock_response = MagicMock()
    mock_response.markdown = None

    with patch("llm_rag.research.subagents.firecrawl.V1FirecrawlApp") as mock_cls:
        mock_app = MagicMock()
        mock_cls.return_value = mock_app
        mock_app.scrape_url.return_value = mock_response

        subagent = FirecrawlSubagent(api_key="test-key")
        result = await subagent.fetch(candidate)

    assert result is None
