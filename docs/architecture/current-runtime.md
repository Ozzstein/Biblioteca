# Current Runtime Architecture (v1)

This document describes the runtime architecture as actually implemented. For planned future architecture, see [roadmap.md](../roadmap.md).

---

## PipelineRunner

**Module:** `src/llm_rag/pipeline/runner.py`

PipelineRunner is a deterministic, sequential document processor. Each document passes through five stages in order:

```
Ingestion → Extraction → Normalization → Wiki Compile → Graph Update
```

### Stage execution

Each stage runs a Claude agent (via `agent_runner.run_agent()`) with a specific set of MCP servers. The runner:

1. Checks the document manifest for already-completed stages and skips them
2. Runs the next pending stage agent
3. Validates the stage output against a Pydantic contract model
4. Updates the manifest with the completed stage
5. Advances to the next stage

### Retry and dead-letter handling

Failed stages are retried with exponential backoff (up to 3 attempts, delays from 2s to 60s). If all retries fail, the document manifest is marked as "dead-lettered" with the error recorded, and the runner moves on to the next document.

### Stage-to-agent mapping

| Stage | Agent | LLM | MCP servers used |
|---|---|---|---|
| `INGESTED` | IngestionAgent | None (pdfplumber + chunking) | corpus_io |
| `EXTRACTED` | ExtractionAgent | Claude Haiku | corpus_io |
| `NORMALIZED` | NormalizationAgent | Claude Haiku + Sonnet | graph_io |
| `WIKI_COMPILED` | WikiCompilerAgent | Claude Sonnet | wiki_io, corpus_io |
| `GRAPH_UPDATED` | GraphCuratorAgent | None (NetworkX) | graph_io |

---

## SupervisorAgent

**Module:** `src/llm_rag/supervisor/loop.py`

The supervisor is a simple async loop (not a state machine). It:

1. Uses APScheduler to schedule research subagent runs at configured intervals
2. Every N seconds (default 60), scans `raw/` for files needing processing
3. Calls `PipelineRunner.run()` for each pending file
4. Runs the ReviewerAgent after pipeline completion

There is no complex state management or graph-based orchestration. The supervisor is a queue consumer with a scheduler.

### File watcher

**Module:** `src/llm_rag/supervisor/watcher.py`

A watchdog `FileSystemEventHandler` monitors `raw/inbox/` for new files and queues them for processing.

---

## QueryAgent

**Module:** `src/llm_rag/query/agent.py`

QueryAgent answers questions against the knowledge base using phased retrieval. There is no separate planner or router — all queries follow the same fixed pipeline:

### Retrieval phases

1. **Evidence phase** — searches Chroma embeddings via `corpus_io.search_chunks` for semantically similar raw text chunks
2. **Wiki phase** — matches wiki page paths to query terms, reads relevant pages via `wiki_io.read_page`
3. **Graph phase** — identifies entities mentioned in the query, expands their neighborhood via `graph_io.get_neighbors`

### Synthesis

After all three retrieval phases complete, the agent bundles the gathered context and calls Claude to synthesize an answer. The synthesis prompt requires inline provenance citations (source document, section, page number) for every claim.

### Quality mode

When `--quality` is passed, the agent uses Claude Opus instead of Sonnet for the synthesis step.

---

## MCP Tool Servers

All agent-to-data-store interactions go through three FastMCP servers running as stdio subprocesses. This provides a clean boundary between agent logic and data access.

### corpus_io

**Module:** `src/llm_rag/mcp/corpus_io.py`

Manages the evidence store (`raw/` + `retrieval/`).

| Tool | Purpose |
|---|---|
| `ingest_file` | Extract text from a raw file (PDF/markdown), chunk it, store chunks as JSONL |
| `search_chunks` | Semantic search over Chroma embeddings |
| `get_chunks` | Retrieve specific chunks by document ID |
| `scan_pending_files` | List files in `raw/` that need processing |
| `save_export` | Write an ExtractionResult JSON to `graph/exports/` |

### wiki_io

**Module:** `src/llm_rag/mcp/wiki_io.py`

Manages the understanding store (`wiki/`).

| Tool | Purpose |
|---|---|
| `create_page` | Create a new wiki page from a template |
| `read_page` | Read a wiki page, returning parsed sections |
| `write_auto_sections` | Update auto-fenced sections (preserves human sections) |
| `list_pages` | List all wiki pages by category |
| `write_provenance` | Write provenance metadata for a wiki page |

Section names are validated against the lowercase-hyphen convention.

### graph_io

**Module:** `src/llm_rag/mcp/graph_io.py`

Manages the relations store (`graph/`).

| Tool | Purpose |
|---|---|
| `merge_extraction` | Merge an ExtractionResult into the live NetworkX graph |
| `get_neighbors` | Get entities connected to a given entity (1-hop) |
| `list_entities` | List all entities, optionally filtered by type |
| `get_entity` | Get a single entity by ID |
| `get_canonical` | Resolve an alias to its canonical entity ID |

The graph is persisted as GraphML snapshots in `graph/snapshots/`.

### MCP server lifecycle

**Module:** `src/llm_rag/mcp/pool.py`

`MCPPool` manages long-lived stdio server processes. Each server is started once and reused across agent invocations within a pipeline run.

---

## Agent Runner

**Module:** `src/llm_rag/agent_runner.py`

Shared infrastructure for running Claude agents:

- Loads system prompts from `agents/prompts/<name>.md` with `{{variable}}` template interpolation
- Wires MCP servers via the Claude Code SDK's `McpStdioServerConfig`
- Runs agents in one-shot mode (`max_turns=1`)
- Streams responses and concatenates text blocks
- Validates tool results against Pydantic schemas

---

## What is NOT in v1

The following items appear in the original design spec but are not implemented:

- **LangGraph state machines** — neither the supervisor nor the query layer use LangGraph. The supervisor is a simple loop; the query agent uses fixed-phase retrieval.
- **Query routing / planning** — all queries follow the same evidence → wiki → graph → synthesis pipeline. There is no intent classification or mode selection.
- **`query/planner.py` and `query/answer.py`** — these files from the design spec do not exist. All query logic is in `query/agent.py`.
- **`query/retrieval.py`** — retrieval functions are embedded in `query/agent.py`, not in a separate module.

See [roadmap.md](../roadmap.md) for the planned v2 architecture.
