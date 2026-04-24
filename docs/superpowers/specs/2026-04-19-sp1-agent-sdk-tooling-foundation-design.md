# SP1: Agent SDK Tooling Foundation — Design Spec

**Date:** 2026-04-19
**Branch:** to be created from `master`
**Status:** Approved, pending implementation plan

---

## Context and Motivation

Battery Research OS uses the Anthropic Python SDK directly today. Each "agent" is a Python class
with a single `client.messages.create()` call and manual JSON parsing. There are no tools, no
agent loops, and `agents/tools/` is empty.

The goal is to migrate all agents to the **Claude Agent SDK** (`claude-agent-sdk` Python package),
giving each agent a true agentic loop with MCP tool access, multi-turn self-correction, and
structured output via `tool_use` rather than fragile JSON parsing.

This spec covers **SP1: Tooling Foundation** — the MCP servers, shared runner, and process
lifecycle management that every subsequent sub-project depends on. SP1 does not migrate any
pipeline agents (that is SP2). It delivers the infrastructure that SP2–SP6 plug into.

---

## Scope

**In scope:**
- Three domain-split MCP servers (`wiki-io`, `graph-io`, `corpus-io`)
- `MCPPool` — long-lived process manager for MCP servers
- `run_agent()` — shared subagent runner that all future agents call
- `AgentDefinition` dataclass
- Tests for each MCP server and the runner
- pyproject.toml entrypoints and dependency additions

**Out of scope (later sub-projects):**
- Migrating `ExtractionAgent`, `WikiCompilerAgent`, etc. (SP2)
- Supervisor `MCPPool` wiring and APScheduler integration (SP3)
- Research subagents (SP4)
- Query layer (SP5)
- CLI (SP6)

---

## Architecture

### Overview

```
Supervisor (SP3)
    │  owns MCPPool lifetime
    ▼
MCPPool  ──starts/monitors──►  wiki-io process (stdio)
                           ►  graph-io process (stdio)
                           ►  corpus-io process (stdio)

Pipeline agent (SP2)
    │  calls
    ▼
run_agent(definition, user_message, settings, mcp_pool)
    │  constructs SDK Agent with MCPServerStdio connections from pool
    ▼
SDK Agent loop
    │  tool calls over stdio
    ▼
MCP server tool functions  ──read/write──►  wiki/, graph/, retrieval/ on disk
```

### Why long-lived MCP processes

The supervisor runs continuously (60s polling loop). Ephemeral per-call server startup would cost
~200–500ms × 3 servers = ~1.5s of pure Python startup overhead on every pipeline dispatch, 
compounding across document batches. Long-lived servers pay startup cost once at supervisor 
launch and then serve all subsequent calls at stdio IPC latency (~1ms).

MCP servers do **not** cache domain objects in memory (graph, manifests, etc.) to avoid stale
reads. Each tool call reads from disk. This keeps correctness simple at the cost of I/O on each
call — acceptable given the batch cadence.

---

## Module Layout

```
src/llm_rag/
  mcp/
    __init__.py
    wiki_io.py        # FastMCP app — wiki-io server
    graph_io.py       # FastMCP app — graph-io server
    corpus_io.py      # FastMCP app — corpus-io server
    pool.py           # MCPPool context manager
  agent_runner.py     # AgentDefinition + run_agent()

tests/
  mcp/
    test_wiki_io.py
    test_graph_io.py
    test_corpus_io.py
  test_agent_runner.py

pyproject.toml        # new scripts + claude-agent-sdk dep
```

**Deleted:**
```
agents/tools/         # currently empty — removed entirely
```

---

## MCP Servers

All three servers follow the same pattern:

```python
from mcp.server.fastmcp import FastMCP

app = FastMCP("wiki-io")   # or "graph-io", "corpus-io"

@app.tool()
async def my_tool(arg: str) -> str:
    ...

if __name__ == "__main__":
    app.run()
```

Each is a pyproject.toml script entrypoint so the SDK can launch it by name.

### `corpus-io` — chunk and manifest operations

Used by: ExtractionAgent, NormalizationAgent, IngestionAgent (SP2)

| Tool | Signature | Description |
|------|-----------|-------------|
| `get_chunks` | `(doc_id: str) → list[dict]` | Read `retrieval/chunks/<doc-id>.jsonl` |
| `get_manifest` | `(doc_id: str) → dict` | Read `raw/**/<doc-id>.manifest.json` |
| `save_manifest` | `(manifest: dict) → None` | Write manifest to its sidecar path |
| `save_export` | `(result: dict) → None` | Write `graph/exports/<doc-id>.json` |
| `list_pending_docs` | `(missing_stage: str) → list[str]` | Manifests lacking a given ProcessingStage |

### `wiki-io` — wiki page read/write

Used by: WikiCompilerAgent, ReviewerAgent (SP2), QueryLayer (SP5)

| Tool | Signature | Description |
|------|-----------|-------------|
| `read_page` | `(path: str) → str` | Raw markdown of a wiki page |
| `write_auto_sections` | `(path: str, sections: dict) → None` | Section-fenced write; preserves human sections |
| `list_pages` | `(subdir: str = "") → list[str]` | Enumerate wiki/ subtree |
| `get_template` | `(page_type: str) → str` | Read `config/page-templates/<type>.md` |
| `create_page` | `(path: str, page_type: str) → None` | Instantiate template and write new page |

### `graph-io` — NetworkX graph operations

Used by: GraphCuratorAgent, NormalizationAgent (SP2), QueryLayer (SP5)

| Tool | Signature | Description |
|------|-----------|-------------|
| `get_entity` | `(entity_id: str) → dict \| None` | Lookup entity from live graph |
| `list_entities` | `(entity_type: str = "") → list[dict]` | Filtered by EntityType if provided |
| `merge_extraction` | `(export_path: str) → None` | Add one ExtractionResult into graph |
| `get_neighbors` | `(entity_id: str, depth: int = 1) → list[dict]` | NetworkX subgraph traversal |
| `get_canonical` | `(alias: str) → str \| None` | entity-normalization.yaml lookup |

**Stub policy:** Tools whose underlying module methods don't exist yet in SP1 raise
`NotImplementedError` with a clear message. The server starts and registers the tool — only
the call fails. This keeps pyproject.toml entrypoints stable across SP1→SP2.

---

## MCPPool

`src/llm_rag/mcp/pool.py`

```python
@dataclass
class MCPServerConfig:
    name: str           # e.g. "wiki-io"
    command: list[str]  # e.g. ["python", "-m", "llm_rag.mcp.wiki_io"]

class MCPPool:
    """Async context manager. Starts MCP server connections on enter,
    terminates them on exit, recreates any that have failed on next access."""

    async def __aenter__(self) -> MCPPool: ...
    async def __aexit__(self, *_) -> None: ...
    def get(self, name: str) -> MCPServerStdio: ...  # returns live connection
```

**Restart policy:** `MCPPool` manages `MCPServerStdio` instances (not raw subprocess handles) —
the SDK's `MCPServerStdio` already owns the subprocess. On `pool.get(name)`, if the connection is
unhealthy (detected via a lightweight ping or exception on last use), the old `MCPServerStdio` is
closed and a new one is constructed from the registered `MCPServerConfig`. No retry loop — one
restart attempt; if it fails again, the exception propagates to the caller. The exact health-check
mechanism depends on the SDK's `MCPServerStdio` API and should be confirmed during implementation.

**Default servers registered:** `wiki-io`, `graph-io`, `corpus-io`. The supervisor (SP3) constructs
`MCPPool` with this default set. Tests construct pools with a subset or mock server.

---

## Shared Subagent Runner

`src/llm_rag/agent_runner.py`

```python
@dataclass
class AgentDefinition:
    name: str                   # matches agents/prompts/<name>.md
    model: str                  # from Settings model assignments
    mcp_servers: list[str]      # names to pull from MCPPool
    max_tokens: int = 8192

async def run_agent(
    definition: AgentDefinition,
    user_message: str,
    settings: Settings,
    mcp_pool: MCPPool,
) -> str:
    """
    Load system prompt from agents/prompts/<definition.name>.md,
    construct SDK Agent with connections from mcp_pool,
    run with user_message, return final text response.
    """
```

**Prompt loading:** Plain file read of `agents/prompts/<name>.md`. Variable substitution
(`{{VAR}}`) is the caller's responsibility before passing `user_message` — the runner does no
templating.

**Return value:** Raw text of the agent's final response. Callers (pipeline agents in SP2) parse
structured output from this text. The agent may have made multiple tool calls before producing it.

**Structured output strategy (SP2 decision):** SP2 will determine whether to add a `submit_result`
tool pattern (agent emits structured output via a final tool call, runner returns the arg dict) or
keep text+JSON parsing. SP1 does not prescribe this — `run_agent` returns `str` and SP2 can
wrap or override as needed.

**No agent caching:** A new SDK `Agent` object is constructed per `run_agent` call. The MCP
*connections* (processes) are reused via `MCPPool`; the agent object itself is cheap to construct.

---

## pyproject.toml Changes

```toml
[project.dependencies]
# add:
claude-agent-sdk = ">=0.1"   # confirm exact PyPI package name + minimum version before implementing

[project.scripts]
# add:
llm-rag-wiki-io = "llm_rag.mcp.wiki_io:main"
llm-rag-graph-io = "llm_rag.mcp.graph_io:main"
llm-rag-corpus-io = "llm_rag.mcp.corpus_io:main"
```

The `main` function in each MCP module calls `app.run()`.

---

## Testing

### MCP server tests (no subprocess)

Import the FastMCP app directly and call tool functions as plain async functions:

```python
from llm_rag.mcp.wiki_io import app

async def test_read_page(tmp_path):
    # write a test wiki page to tmp_path, call tool function directly
    ...
```

No subprocess, no stdio — fast and isolated. Each server module exports its tool functions so
they are importable without starting the process.

### Agent runner smoke test

Spins up one real MCP server subprocess with a single trivial tool (`echo`), constructs an
`AgentDefinition`, calls `run_agent`, and asserts a non-empty response is returned. This is the
only test that touches a live subprocess and a live Claude API call — it is skipped if
`ANTHROPIC_API_KEY` is not set.

---

## What Does Not Change in SP1

- `src/llm_rag/pipeline/` — all five pipeline agent classes remain. SP2 replaces them.
- `src/llm_rag/supervisor/loop.py` — supervisor still uses its current LangGraph loop. SP3 adds
  `MCPPool` lifecycle wiring.
- `agents/prompts/` — existing `.md` files are unchanged and already in the correct format.
- All schemas, config, wiki, graph, and util modules — untouched.

---

## Success Criteria

1. `uv run python -m llm_rag.mcp.wiki_io` starts without error
2. `uv run python -m llm_rag.mcp.graph_io` starts without error
3. `uv run python -m llm_rag.mcp.corpus_io` starts without error
4. All MCP tool function unit tests pass without subprocess or API calls
5. Agent runner smoke test passes (skipped if no API key)
6. `uv run mypy src/` passes with no new errors
7. `uv run pytest tests/mcp/ tests/test_agent_runner.py -v` all green
