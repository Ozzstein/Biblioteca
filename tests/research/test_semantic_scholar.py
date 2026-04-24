from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.semantic_scholar import SemanticScholarSubagent

_S2_RESPONSE = {
    "data": [
        {
            "paperId": "abc123",
            "title": "LFP Capacity Fade Analysis",
            "abstract": "This paper investigates LFP capacity fade.",
            "year": 2024,
            "authors": [{"authorId": "1", "name": "Alice Researcher"}],
            "externalIds": {"DOI": "10.1016/j.example.2024.001", "ArXiv": "2301.00001"},
            "openAccessPdf": {"url": "https://example.com/paper.pdf", "status": "GREEN"},
        }
    ]
}


def _mock_s2_get(response_data: dict) -> AsyncMock:
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value=response_data)
    mock_response.raise_for_status = MagicMock()
    return mock_response


async def test_s2_search_returns_candidates():
    with patch("llm_rag.research.subagents.semantic_scholar.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_s2_get(_S2_RESPONSE))

        subagent = SemanticScholarSubagent(max_results=15)
        candidates = await subagent.search(["LFP degradation"])

    assert len(candidates) == 1
    c = candidates[0]
    assert c.title == "LFP Capacity Fade Analysis"
    assert c.abstract == "This paper investigates LFP capacity fade."
    assert c.doi == "10.1016/j.example.2024.001"
    assert c.arxiv_id == "2301.00001"
    assert c.pdf_url == "https://example.com/paper.pdf"
    assert c.published_year == 2024
    assert c.authors == ["Alice Researcher"]
    assert c.source == "semantic_scholar"


async def test_s2_search_handles_missing_abstract():
    data = {
        "data": [
            {
                "paperId": "xyz",
                "title": "No Abstract Paper",
                "abstract": None,
                "year": 2023,
                "authors": [],
                "externalIds": {},
                "openAccessPdf": None,
            }
        ]
    }

    with patch("llm_rag.research.subagents.semantic_scholar.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_s2_get(data))

        subagent = SemanticScholarSubagent(max_results=15)
        candidates = await subagent.search(["topic"])

    assert candidates[0].abstract == ""
    assert candidates[0].doi is None
    assert candidates[0].pdf_url is None


async def test_s2_search_handles_empty_data():
    with patch("llm_rag.research.subagents.semantic_scholar.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_s2_get({"data": []}))

        subagent = SemanticScholarSubagent(max_results=15)
        candidates = await subagent.search(["topic"])

    assert candidates == []


async def test_s2_fetch_returns_pdf_bytes():
    candidate = CandidateDocument(
        title="LFP Paper",
        abstract="Abstract.",
        source="semantic_scholar",
        pdf_url="https://example.com/paper.pdf",
    )
    mock_response = AsyncMock()
    mock_response.content = b"%PDF-1.4 s2"
    mock_response.raise_for_status = MagicMock()

    with patch("llm_rag.research.subagents.semantic_scholar.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)

        subagent = SemanticScholarSubagent(max_results=15)
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "pdf"
    assert content == b"%PDF-1.4 s2"


async def test_s2_fetch_returns_none_when_no_pdf_url():
    candidate = CandidateDocument(
        title="LFP Paper", abstract="Abstract.", source="semantic_scholar", pdf_url=None
    )
    subagent = SemanticScholarSubagent(max_results=15)
    result = await subagent.fetch(candidate)
    assert result is None
