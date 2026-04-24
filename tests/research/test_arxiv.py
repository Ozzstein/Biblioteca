from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.arxiv import ArXivSubagent


def _make_arxiv_result(
    title: str = "LFP Degradation Study",
    summary: str = "We study LFP capacity fade.",
    doi: str | None = "10.1016/j.electacta.2024.001",
    entry_id: str = "http://arxiv.org/abs/2301.00001v1",
    pdf_url: str | None = "https://arxiv.org/pdf/2301.00001",
    year: int = 2024,
) -> MagicMock:
    result = MagicMock()
    result.title = title
    result.summary = summary
    result.doi = doi
    result.entry_id = entry_id
    result.pdf_url = pdf_url
    result.published = MagicMock(year=year)
    author = MagicMock()
    author.__str__ = lambda self: "A. Researcher"
    result.authors = [author]
    return result


async def test_arxiv_search_returns_candidates():
    mock_result = _make_arxiv_result()

    with patch("llm_rag.research.subagents.arxiv.arxiv.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.results.return_value = iter([mock_result])

        subagent = ArXivSubagent(max_results=20)
        candidates = await subagent.search(["LFP degradation"])

    assert len(candidates) == 1
    c = candidates[0]
    assert c.title == "LFP Degradation Study"
    assert c.abstract == "We study LFP capacity fade."
    assert c.doi == "10.1016/j.electacta.2024.001"
    assert c.arxiv_id == "2301.00001v1"
    assert c.pdf_url == "https://arxiv.org/pdf/2301.00001"
    assert c.published_year == 2024
    assert c.authors == ["A. Researcher"]
    assert c.source == "arxiv"


async def test_arxiv_search_multiple_topics_aggregated():
    r1 = _make_arxiv_result(title="Paper 1", doi="10.1/a")
    r2 = _make_arxiv_result(title="Paper 2", doi="10.1/b")

    with patch("llm_rag.research.subagents.arxiv.arxiv.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.results.side_effect = [iter([r1]), iter([r2])]

        subagent = ArXivSubagent(max_results=20)
        candidates = await subagent.search(["topic A", "topic B"])

    assert len(candidates) == 2


async def test_arxiv_search_null_doi_handled():
    mock_result = _make_arxiv_result(doi=None)

    with patch("llm_rag.research.subagents.arxiv.arxiv.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.results.return_value = iter([mock_result])

        subagent = ArXivSubagent(max_results=20)
        candidates = await subagent.search(["LFP"])

    assert candidates[0].doi is None


async def test_arxiv_fetch_returns_pdf_bytes():
    candidate = CandidateDocument(
        title="LFP Paper",
        abstract="Abstract.",
        source="arxiv",
        pdf_url="https://arxiv.org/pdf/2301.00001",
    )
    mock_response = AsyncMock()
    mock_response.content = b"%PDF-1.4 test"
    mock_response.raise_for_status = MagicMock()

    with patch("llm_rag.research.subagents.arxiv.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)

        subagent = ArXivSubagent(max_results=20)
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "pdf"
    assert content == b"%PDF-1.4 test"


async def test_arxiv_fetch_returns_none_when_no_pdf_url():
    candidate = CandidateDocument(
        title="LFP Paper", abstract="Abstract.", source="arxiv", pdf_url=None
    )
    subagent = ArXivSubagent(max_results=20)
    result = await subagent.fetch(candidate)
    assert result is None
