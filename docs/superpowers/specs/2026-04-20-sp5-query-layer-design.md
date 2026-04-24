# SP5: Query Layer — Design Spec

**Date:** 2026-04-20
**Status:** Approved

---

## Goal

Build the query layer natively on the Agent SDK. A single `QueryAgent` wraps `run_agent()` with all three MCP servers wired up (wiki-io, graph-io, corpus-io). Claude retrieves and synthesizes in one agentic loop. No LangGraph, no explicit routing code.

---

## What This Builds

- `src/llm_rag/query/agent.py` — `QueryAgent` class + `QueryResult` dataclass + `_parse_result()` helper
- `agents/prompts/query_agent.md` — system prompt with retrieval instructions and citation format
- `search_chunks` MCP tool added to `src/llm_rag/mcp/corpus_io.py`
- Tests: `tests/query/test_agent.py` (new) + 2 additions to `tests/mcp/test_corpus_io.py`

## What This Does Not Build

- CLI wiring (`llm-rag ask`) — that is SP6
- `--mode` routing flags — deferred; Claude always decides retrieval strategy
- `--quality` / `--verbose` flags — deferred to SP6

---

## Section 1: `search_chunks` MCP Tool

New tool added to `src/llm_rag/mcp/corpus_io.py`:

```python
@app.tool()
async def search_chunks(query: str, n_results: int = 5) -> list[dict[str, Any]]:
    """Semantic similarity search over all ingested document chunks."""
    collection = _get_collection()
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas"],
    )
    chunks = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        chunks.append({
            "text": doc,
            "doc_id": meta.get("doc_id", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "section": meta.get("section", ""),
        })
    return chunks
```

The Chroma collection is accessed via the existing `_get_collection()` singleton. If the collection is empty (no documents ingested), `collection.query()` returns empty lists and the tool returns `[]`.

---

## Section 2: `QueryAgent` and `QueryResult`

New file `src/llm_rag/query/agent.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from llm_rag.agent_runner import AgentDefinition, run_agent
from llm_rag.config import Settings, get_settings
from llm_rag.mcp.pool import MCPPool


@dataclass
class QueryResult:
    answer: str
    sources: list[str] = field(default_factory=list)


def _parse_result(raw: str) -> QueryResult:
    if "## Sources" in raw:
        answer_part, _, sources_part = raw.partition("## Sources")
        sources = [
            line.lstrip("- ").strip()
            for line in sources_part.strip().splitlines()
            if line.strip().startswith("-")
        ]
        return QueryResult(answer=answer_part.strip(), sources=sources)
    return QueryResult(answer=raw.strip(), sources=[])


class QueryAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._agent = AgentDefinition(
            name="query_agent",
            model=self.settings.model_query_synthesis,
            mcp_servers=["wiki-io", "graph-io", "corpus-io"],
            max_tokens=4096,
        )

    async def ask(self, query: str, pool: MCPPool) -> QueryResult:
        raw = await run_agent(self._agent, query, self.settings, pool)
        return _parse_result(raw)
```

`QueryAgent` is the public interface. Callers (SP6 CLI) create a `QueryAgent`, open an `MCPPool`, and call `ask()`. The `MCPPool` is owned by the caller so it can be shared across multiple queries in a session.

---

## Section 3: `agents/prompts/query_agent.md`

```markdown
You are the Query Agent for the Battery Research OS, a knowledge base about battery materials and electrochemistry.

You have access to three retrieval sources:

**wiki-io** (structured knowledge pages):
- `list_pages(subdir="")` — list all wiki pages
- `read_page(relative_path)` — read a wiki page's markdown content

**graph-io** (entity relationship graph):
- `list_entities(entity_type="")` — list known entities
- `get_entity(entity_id)` — get entity attributes
- `get_neighbors(entity_id, depth=1)` — get related entities
- `get_canonical(alias)` — resolve an alias to a canonical entity ID

**corpus-io** (raw document evidence):
- `search_chunks(query, n_results=5)` — semantic search over ingested document chunks
- `get_chunks(doc_id)` — read all chunks for a specific document

## Instructions

1. Analyze the question and decide which sources to consult.
2. Call the relevant tools to gather evidence. For mechanistic questions, prefer wiki. For entity relationships, prefer graph. For specific evidence from papers, use search_chunks.
3. Synthesize a clear, accurate markdown answer.
4. End your response with a `## Sources` section listing every source consulted, one per line prefixed with `-`:

```
## Sources
- wiki/materials/lfp.md §evidence
- papers/lfp-capacity-fade-2024 (chunk 3)
- entity:mechanism:sei
```

If you find no relevant information, say so clearly rather than guessing.
```

---

## Section 4: Testing

### `tests/mcp/test_corpus_io.py` — 2 additions

```python
async def test_search_chunks_returns_matching_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["LFP shows 170 mAh/g capacity."]],
        "metadatas": [
            [{"doc_id": "papers/lfp-001", "chunk_index": 2, "section": "results"}]
        ],
    }
    monkeypatch.setattr("llm_rag.mcp.corpus_io._get_collection", lambda: mock_collection)
    from llm_rag.mcp.corpus_io import search_chunks
    result = await search_chunks("LFP capacity")
    assert len(result) == 1
    assert result[0]["text"] == "LFP shows 170 mAh/g capacity."
    assert result[0]["doc_id"] == "papers/lfp-001"
    assert result[0]["chunk_index"] == 2
    assert result[0]["section"] == "results"
    get_settings.cache_clear()


async def test_search_chunks_empty_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [[]],
        "metadatas": [[]],
    }
    monkeypatch.setattr("llm_rag.mcp.corpus_io._get_collection", lambda: mock_collection)
    from llm_rag.mcp.corpus_io import search_chunks
    result = await search_chunks("LFP capacity")
    assert result == []
    get_settings.cache_clear()
```

### `tests/query/test_agent.py` — new file

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.config import Settings
from llm_rag.query.agent import QueryAgent, QueryResult, _parse_result


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        root_dir=tmp_path,
        model_query_synthesis="claude-sonnet-4-6",
    )


def _mock_pool() -> tuple[MagicMock, MagicMock]:
    mock_pool_instance = MagicMock()
    mock_pool_cls = MagicMock()
    mock_pool_cls.return_value.__aenter__ = AsyncMock(return_value=mock_pool_instance)
    mock_pool_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_pool_cls, mock_pool_instance


def test_parse_result_no_sources_section():
    raw = "LFP shows capacity fade at high temperatures."
    result = _parse_result(raw)
    assert result.answer == "LFP shows capacity fade at high temperatures."
    assert result.sources == []


def test_parse_result_extracts_source_lines():
    raw = "LFP capacity fade is well documented.\n\n## Sources\n- wiki/materials/lfp.md §evidence\n- papers/lfp-001 (chunk 3)\n\nSome trailing text."
    result = _parse_result(raw)
    assert result.answer == "LFP capacity fade is well documented."
    assert result.sources == ["wiki/materials/lfp.md §evidence", "papers/lfp-001 (chunk 3)"]


async def test_ask_returns_query_result(tmp_path: Path):
    settings = _make_settings(tmp_path)
    mock_pool = MagicMock()
    raw_response = (
        "LFP capacity fade is caused by SEI growth.\n\n"
        "## Sources\n- wiki/mechanisms/sei.md §evidence\n- papers/lfp-001 (chunk 2)"
    )
    with patch("llm_rag.query.agent.run_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = raw_response
        agent = QueryAgent(settings=settings)
        result = await agent.ask("What causes LFP capacity fade?", mock_pool)
    assert "SEI growth" in result.answer
    assert len(result.sources) == 2
    assert result.sources[0] == "wiki/mechanisms/sei.md §evidence"
```

---

## File Layout Summary

**Created:**
```
src/llm_rag/query/agent.py
agents/prompts/query_agent.md
tests/query/__init__.py
tests/query/test_agent.py
```

**Modified:**
```
src/llm_rag/mcp/corpus_io.py    — add search_chunks tool
tests/mcp/test_corpus_io.py     — add 2 search_chunks tests
```
