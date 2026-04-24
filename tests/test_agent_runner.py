from __future__ import annotations

import os
from pathlib import Path

import pytest

from llm_rag.agent_runner import AgentDefinition


def test_agent_definition_defaults() -> None:
    defn = AgentDefinition(
        name="extraction",
        model="claude-haiku-4-5-20251001",
        mcp_servers=["corpus-io"],
    )
    assert defn.max_tokens == 8192
    assert defn.name == "extraction"


def test_agent_definition_prompt_path_derived(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    defn = AgentDefinition(
        name="extraction",
        model="claude-haiku-4-5-20251001",
        mcp_servers=["corpus-io"],
    )
    settings = get_settings()
    expected = settings.agents_dir / "prompts" / "extraction.md"
    assert defn.prompt_path(settings) == expected
    get_settings.cache_clear()


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="requires ANTHROPIC_API_KEY")
async def test_run_agent_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke test: runner constructs agent, calls it, returns non-empty string."""
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()

    prompts_dir = tmp_path / "agents" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "smoke.md").write_text("You are a helpful assistant. Answer in one word.")

    from llm_rag.agent_runner import AgentDefinition, run_agent
    from llm_rag.mcp.pool import MCPPool

    defn = AgentDefinition(name="smoke", model="claude-haiku-4-5-20251001", mcp_servers=[])
    settings = get_settings()

    async with MCPPool(servers=[]) as pool:
        result = await run_agent(defn, "Say hello.", settings, pool)

    assert isinstance(result, str)
    assert len(result) > 0
    get_settings.cache_clear()
