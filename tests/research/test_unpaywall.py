from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.unpaywall import UnpaywallSubagent

_UNPAYWALL_RESPONSE = {
    "doi": "10.1016/j.example.2024",
    "title": "LFP Open Access Study",
    "z_authors": [{"given": "D.", "family": "Researcher"}],
    "year": 2024,
    "best_oa_location": {
        "url_for_pdf": "https://example.com/oa-paper.pdf",
        "url": "https://example.com/oa-paper",
    },
}


def _mock_resp(data: dict) -> AsyncMock:
    r = AsyncMock()
    r.json = MagicMock(return_value=data)
    r.raise_for_status = MagicMock()
    return r


def _mock_pdf_resp() -> AsyncMock:
    r = AsyncMock()
    r.content = b"%PDF-1.4 unpaywall"
    r.raise_for_status = MagicMock()
    return r


async def test_unpaywall_search_returns_empty():
    subagent = UnpaywallSubagent(email="test@example.com")
    results = await subagent.search(["LFP"])
    assert results == []


async def test_unpaywall_fetch_resolves_doi_and_downloads_pdf():
    candidate = CandidateDocument(
        title="LFP Study",
        abstract="Abstract.",
        source="unpaywall",
        doi="10.1016/j.example.2024",
    )

    with patch("llm_rag.research.subagents.unpaywall.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=[
            _mock_resp(_UNPAYWALL_RESPONSE),
            _mock_pdf_resp(),
        ])

        subagent = UnpaywallSubagent(email="test@example.com")
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "pdf"
    assert content == b"%PDF-1.4 unpaywall"


async def test_unpaywall_fetch_returns_none_when_no_doi():
    candidate = CandidateDocument(
        title="No DOI", abstract="Abstract.", source="unpaywall", doi=None
    )
    subagent = UnpaywallSubagent(email="test@example.com")
    result = await subagent.fetch(candidate)
    assert result is None


async def test_unpaywall_fetch_returns_none_when_no_oa_location():
    candidate = CandidateDocument(
        title="Paywalled", abstract="Abstract.", source="unpaywall", doi="10.1/paywalled"
    )
    no_oa = {"doi": "10.1/paywalled", "title": "Paywalled", "year": 2024, "best_oa_location": None}

    with patch("llm_rag.research.subagents.unpaywall.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_resp(no_oa))

        subagent = UnpaywallSubagent(email="test@example.com")
        result = await subagent.fetch(candidate)

    assert result is None
