from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.openalex import OpenAlexSubagent

_OA_RESPONSE = {
    "results": [
        {
            "id": "https://openalex.org/W123456",
            "title": "LFP Structural Stability",
            "abstract_inverted_index": {
                "We": [0],
                "investigate": [1],
                "LFP": [2],
                "stability.": [3],
            },
            "doi": "https://doi.org/10.1016/j.example.2024.001",
            "publication_year": 2024,
            "authorships": [{"author": {"display_name": "B. Scientist"}}],
            "primary_location": {"pdf_url": "https://example.com/oa-paper.pdf"},
        }
    ]
}


def _mock_oa_get(response_data: dict) -> AsyncMock:
    mock_response = AsyncMock()
    mock_response.json = MagicMock(return_value=response_data)
    mock_response.raise_for_status = MagicMock()
    return mock_response


async def test_openalex_search_returns_candidates():
    with patch("llm_rag.research.subagents.openalex.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_oa_get(_OA_RESPONSE))

        subagent = OpenAlexSubagent(max_results=20)
        candidates = await subagent.search(["LFP stability"])

    assert len(candidates) == 1
    c = candidates[0]
    assert c.title == "LFP Structural Stability"
    assert c.abstract == "We investigate LFP stability."
    assert c.doi == "10.1016/j.example.2024.001"
    assert c.pdf_url == "https://example.com/oa-paper.pdf"
    assert c.published_year == 2024
    assert c.authors == ["B. Scientist"]
    assert c.source == "openalex"


async def test_openalex_search_handles_null_abstract():
    data = {
        "results": [
            {
                "id": "https://openalex.org/W999",
                "title": "No Abstract",
                "abstract_inverted_index": None,
                "doi": None,
                "publication_year": None,
                "authorships": [],
                "primary_location": None,
            }
        ]
    }

    with patch("llm_rag.research.subagents.openalex.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_oa_get(data))

        subagent = OpenAlexSubagent(max_results=20)
        candidates = await subagent.search(["topic"])

    assert candidates[0].abstract == ""
    assert candidates[0].doi is None
    assert candidates[0].pdf_url is None


async def test_openalex_doi_prefix_stripped():
    data = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "title": "Test",
                "abstract_inverted_index": None,
                "doi": "https://doi.org/10.1234/test",
                "publication_year": 2024,
                "authorships": [],
                "primary_location": None,
            }
        ]
    }

    with patch("llm_rag.research.subagents.openalex.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_oa_get(data))

        subagent = OpenAlexSubagent(max_results=20)
        candidates = await subagent.search(["topic"])

    assert candidates[0].doi == "10.1234/test"


async def test_openalex_fetch_returns_pdf_bytes():
    candidate = CandidateDocument(
        title="OA Paper", abstract="Abstract.", source="openalex",
        pdf_url="https://example.com/oa.pdf",
    )
    mock_response = AsyncMock()
    mock_response.content = b"%PDF-1.4 oa"
    mock_response.raise_for_status = MagicMock()

    with patch("llm_rag.research.subagents.openalex.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)

        subagent = OpenAlexSubagent(max_results=20)
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "pdf"
    assert content == b"%PDF-1.4 oa"


async def test_openalex_fetch_returns_none_when_no_pdf_url():
    candidate = CandidateDocument(
        title="OA Paper", abstract="Abstract.", source="openalex", pdf_url=None
    )
    subagent = OpenAlexSubagent(max_results=20)
    result = await subagent.fetch(candidate)
    assert result is None
