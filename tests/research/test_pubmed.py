from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.pubmed import PubMedSubagent

_ESEARCH_RESPONSE = {
    "esearchresult": {"idlist": ["38000001", "38000002"]}
}

_ESUMMARY_RESPONSE = {
    "result": {
        "uids": ["38000001", "38000002"],
        "38000001": {
            "uid": "38000001",
            "title": "LFP Battery Cycle Life Study",
            "authors": [{"name": "C. Researcher"}],
            "pubdate": "2024 Jan",
            "articleids": [
                {"idtype": "doi", "value": "10.1016/j.example.2024.001"},
                {"idtype": "pubmed", "value": "38000001"},
            ],
        },
        "38000002": {
            "uid": "38000002",
            "title": "NMC Cathode Structural Analysis",
            "authors": [],
            "pubdate": "2023 Nov",
            "articleids": [],
        },
    }
}


def _mock_response(data: dict) -> AsyncMock:
    r = AsyncMock()
    r.json = MagicMock(return_value=data)
    r.raise_for_status = MagicMock()
    return r


async def test_pubmed_search_returns_candidates():
    responses = [
        _mock_response(_ESEARCH_RESPONSE),
        _mock_response(_ESUMMARY_RESPONSE),
    ]

    with patch("llm_rag.research.subagents.pubmed.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=responses)

        subagent = PubMedSubagent(max_results=10)
        candidates = await subagent.search(["LFP degradation"])

    assert len(candidates) == 2
    c = candidates[0]
    assert c.title == "LFP Battery Cycle Life Study"
    assert c.doi == "10.1016/j.example.2024.001"
    assert c.published_year == 2024
    assert c.authors == ["C. Researcher"]
    assert c.source == "pubmed"
    assert c.abstract == ""


async def test_pubmed_search_handles_no_doi():
    with patch("llm_rag.research.subagents.pubmed.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        esearch = _mock_response({"esearchresult": {"idlist": ["38000002"]}})
        esummary = _mock_response(
            {
                "result": {
                    "uids": ["38000002"],
                    "38000002": {
                        "uid": "38000002",
                        "title": "No DOI Paper",
                        "authors": [],
                        "pubdate": "2023",
                        "articleids": [],
                    },
                }
            }
        )
        mock_http.get = AsyncMock(side_effect=[esearch, esummary])

        subagent = PubMedSubagent(max_results=10)
        candidates = await subagent.search(["topic"])

    assert candidates[0].doi is None


async def test_pubmed_search_empty_idlist():
    with patch("llm_rag.research.subagents.pubmed.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_response({"esearchresult": {"idlist": []}}))

        subagent = PubMedSubagent(max_results=10)
        candidates = await subagent.search(["topic"])

    assert candidates == []


async def test_pubmed_fetch_returns_none():
    candidate = CandidateDocument(title="T", abstract="A", source="pubmed")
    subagent = PubMedSubagent(max_results=10)
    result = await subagent.fetch(candidate)
    assert result is None
