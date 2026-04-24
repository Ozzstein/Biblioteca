from __future__ import annotations

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.google_scholar import GoogleScholarSubagent


async def test_google_scholar_search_returns_empty():
    subagent = GoogleScholarSubagent(serpapi_key="")
    results = await subagent.search(["LFP"])
    assert results == []


async def test_google_scholar_search_returns_empty_with_key():
    subagent = GoogleScholarSubagent(serpapi_key="fake-key")
    results = await subagent.search(["LFP"])
    assert results == []


async def test_google_scholar_fetch_returns_none():
    candidate = CandidateDocument(
        title="LFP Paper", abstract="Abstract.", source="google_scholar"
    )
    subagent = GoogleScholarSubagent(serpapi_key="")
    result = await subagent.fetch(candidate)
    assert result is None
