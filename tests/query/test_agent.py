from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.config import Settings
from llm_rag.query.agent import QueryAgent, _parse_result


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        ANTHROPIC_API_KEY="test-key",
        root_dir=tmp_path,
        model_query_synthesis="claude-sonnet-4-6",
    )


def test_parse_result_no_sources_section() -> None:
    raw = "LFP shows capacity fade at high temperatures."
    result = _parse_result(raw)
    assert result.answer == "LFP shows capacity fade at high temperatures."
    assert result.sources == []


def test_parse_result_extracts_source_lines() -> None:
    raw = (
        "LFP capacity fade is well documented.\n\n"
        "## Sources\n"
        "- wiki/materials/lfp.md §evidence\n"
        "- papers/lfp-001 (chunk 3)\n\n"
        "Some trailing text."
    )
    result = _parse_result(raw)
    assert result.answer == "LFP capacity fade is well documented."
    assert result.sources == [
        "wiki/materials/lfp.md §evidence",
        "papers/lfp-001 (chunk 3)",
    ]


async def test_ask_returns_query_result(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mock_pool = MagicMock()
    raw_response = (
        "LFP capacity fade is caused by SEI growth.\n\n"
        "## Sources\n"
        "- wiki/mechanisms/sei.md §evidence\n"
        "- papers/lfp-001 (chunk 2)"
    )
    with (
        patch("llm_rag.query.agent.run_agent", new_callable=AsyncMock) as mock_run,
        patch("llm_rag.query.agent.retrieve_evidence", new_callable=AsyncMock) as mock_ev,
        patch("llm_rag.query.agent.retrieve_wiki", new_callable=AsyncMock) as mock_wiki,
        patch("llm_rag.query.agent.retrieve_graph", new_callable=AsyncMock) as mock_graph,
    ):
        mock_run.return_value = raw_response
        mock_ev.return_value = []
        mock_wiki.return_value = []
        mock_graph.return_value = []
        agent = QueryAgent(settings=settings)
        result = await agent.ask("What causes LFP capacity fade?", mock_pool)
    assert "SEI growth" in result.answer
    assert len(result.sources) == 2
    assert result.sources[0] == "wiki/mechanisms/sei.md §evidence"
    assert result.sources[1] == "papers/lfp-001 (chunk 2)"
