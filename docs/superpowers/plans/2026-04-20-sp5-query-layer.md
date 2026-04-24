# SP5: Query Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the query layer natively on the Agent SDK — a `QueryAgent` that retrieves from wiki, graph, and corpus via MCP tools and synthesizes a structured markdown answer with provenance citations.

**Architecture:** A single `AgentDefinition` wires up all three MCP servers (wiki-io, graph-io, corpus-io). `QueryAgent.ask()` calls `run_agent()` and parses the `## Sources` section out of the response into a `QueryResult(answer, sources)` dataclass. A new `search_chunks` tool is added to corpus-io to enable semantic similarity search over ingested document chunks.

**Tech Stack:** `claude-code-sdk` (`run_agent`, `AgentDefinition`), `chromadb` (via existing `_get_collection()` singleton), `llm_rag.mcp.pool.MCPPool`, `unittest.mock` (AsyncMock, patch), pytest asyncio_mode=auto.

---

## File Layout

| File | Action | Purpose |
|------|--------|---------|
| `src/llm_rag/mcp/corpus_io.py` | **Modify** | Add `search_chunks` tool (semantic similarity search via Chroma) |
| `src/llm_rag/query/agent.py` | **Create** | `QueryResult` dataclass, `_parse_result()` helper, `QueryAgent` class |
| `agents/prompts/query_agent.md` | **Create** | System prompt with retrieval instructions and citation format |
| `tests/query/__init__.py` | **Create** | Empty — makes `tests/query/` a package |
| `tests/query/test_agent.py` | **Create** | 3 tests for `_parse_result` and `QueryAgent.ask` |
| `tests/mcp/test_corpus_io.py` | **Modify** | Add 2 tests for `search_chunks` |

---

## Task 1: Add `search_chunks` to corpus-io

**Files:**
- Modify: `src/llm_rag/mcp/corpus_io.py`
- Test: `tests/mcp/test_corpus_io.py`

Context: `corpus_io.py` already has `_get_collection()` which returns the Chroma `Collection` singleton. The `collection.query()` method takes `query_texts`, `n_results`, and `include` kwargs and returns a dict with `"documents"` and `"metadatas"` keys. Each is a list-of-lists (one inner list per query text — we always pass one query).

- [ ] **Step 1: Write the two failing tests**

Append to `tests/mcp/test_corpus_io.py`:

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

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/mcp/test_corpus_io.py::test_search_chunks_returns_matching_chunks tests/mcp/test_corpus_io.py::test_search_chunks_empty_collection -v
```

Expected: `ImportError` — `search_chunks` not yet defined.

- [ ] **Step 3: Add `search_chunks` to `corpus_io.py`**

Insert the following before the `def main()` line at the bottom of `src/llm_rag/mcp/corpus_io.py`:

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

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/mcp/test_corpus_io.py -v
```

Expected: all corpus_io tests pass, including the 2 new ones.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/mcp/corpus_io.py tests/mcp/test_corpus_io.py
git commit -m "feat: add search_chunks semantic search tool to corpus-io"
```

---

## Task 2: Create the query agent prompt

**Files:**
- Create: `agents/prompts/query_agent.md`

No test needed — prompt files are only exercised via live API calls.

- [ ] **Step 1: Create `agents/prompts/query_agent.md`**

Write the following content exactly:

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

- [ ] **Step 2: Verify the file exists**

```bash
cat agents/prompts/query_agent.md
```

Expected: the prompt content above.

- [ ] **Step 3: Commit**

```bash
git add agents/prompts/query_agent.md
git commit -m "feat: add query_agent prompt"
```

---

## Task 3: Create `QueryAgent` and its tests

**Files:**
- Create: `src/llm_rag/query/agent.py`
- Create: `tests/query/__init__.py`
- Create: `tests/query/test_agent.py`

Context:
- `run_agent(definition, user_message, settings, pool)` is in `llm_rag.agent_runner` — returns `str`
- `AgentDefinition(name, model, mcp_servers, max_tokens)` is in `llm_rag.agent_runner`
- `MCPPool` is in `llm_rag.mcp.pool`
- `Settings` is in `llm_rag.config`; `settings.model_query_synthesis` is `"claude-sonnet-4-6"` by default
- `asyncio_mode = "auto"` in pytest — no `@pytest.mark.asyncio` decorator needed

- [ ] **Step 1: Create the empty test package**

```bash
touch tests/query/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/query/test_agent.py` with:

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


def test_parse_result_no_sources_section():
    raw = "LFP shows capacity fade at high temperatures."
    result = _parse_result(raw)
    assert result.answer == "LFP shows capacity fade at high temperatures."
    assert result.sources == []


def test_parse_result_extracts_source_lines():
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


async def test_ask_returns_query_result(tmp_path: Path):
    settings = _make_settings(tmp_path)
    mock_pool = MagicMock()
    raw_response = (
        "LFP capacity fade is caused by SEI growth.\n\n"
        "## Sources\n"
        "- wiki/mechanisms/sei.md §evidence\n"
        "- papers/lfp-001 (chunk 2)"
    )
    with patch("llm_rag.query.agent.run_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = raw_response
        agent = QueryAgent(settings=settings)
        result = await agent.ask("What causes LFP capacity fade?", mock_pool)
    assert "SEI growth" in result.answer
    assert len(result.sources) == 2
    assert result.sources[0] == "wiki/mechanisms/sei.md §evidence"
    assert result.sources[1] == "papers/lfp-001 (chunk 2)"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/query/test_agent.py -v
```

Expected: `ModuleNotFoundError` — `llm_rag.query.agent` does not exist yet.

- [ ] **Step 4: Create `src/llm_rag/query/agent.py`**

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

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/query/test_agent.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 6: Run mypy**

```bash
uv run mypy src/llm_rag/query/agent.py
```

Expected: `Success: no issues found in 1 source file`

- [ ] **Step 7: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass (159 previously passing + 3 new query tests + 2 new corpus_io tests = 164 passing, 1 skipped).

- [ ] **Step 8: Commit**

```bash
git add src/llm_rag/query/agent.py tests/query/__init__.py tests/query/test_agent.py
git commit -m "feat: add QueryAgent and QueryResult for SDK-native query layer"
```
