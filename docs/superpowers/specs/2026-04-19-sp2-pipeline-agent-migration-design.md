# SP2: Pipeline Agent Migration — Design Spec

**Date:** 2026-04-19
**Status:** Approved

---

## Goal

Migrate all five pipeline stages to Claude Agent SDK agents. Each stage becomes an `AgentDefinition` + `run_agent()` call. Python pipeline classes are deleted; their deterministic logic moves into MCP tool implementations that Claude calls autonomously.

## Architecture

### What changes

All five pipeline Python classes are deleted:

- `src/llm_rag/pipeline/ingestion.py` — `IngestionAgent` class removed
- `src/llm_rag/pipeline/extraction.py` — `ExtractionAgent` class removed
- `src/llm_rag/pipeline/normalization.py` — `NormalizationAgent` class removed
- `src/llm_rag/pipeline/wiki_compiler.py` — `WikiCompilerAgent` class removed
- `src/llm_rag/pipeline/graph_curator.py` — `GraphCuratorAgent` class removed

The Python logic inside those classes does not disappear — it moves into MCP tool implementations where Claude can invoke it via tool calls.

### What replaces them

Five `AgentDefinition` instances built inside `PipelineRunner.__init__` using `self.settings`:

```python
class PipelineRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pool: MCPPool | None = None
        self._ingestion = AgentDefinition("ingestion", settings.model_bulk_extraction, ["corpus-io"], max_tokens=4096)
        self._extraction = AgentDefinition("extraction", settings.model_bulk_extraction, ["corpus-io"], max_tokens=8192)
        self._normalization = AgentDefinition("normalization", settings.model_bulk_extraction, ["corpus-io", "graph-io"], max_tokens=8192)
        self._wiki_compiler = AgentDefinition("wiki_compiler", settings.model_wiki_compilation, ["corpus-io", "wiki-io"], max_tokens=8192)
        self._graph_curator = AgentDefinition("graph_curator", settings.model_bulk_extraction, ["corpus-io", "graph-io"], max_tokens=4096)
```

`PipelineRunner.__init__` drops all five agent constructor arguments and accepts only `settings: Settings`. It becomes an async context manager that owns a long-lived `MCPPool`.

---

## Stage Ownership After SP2

| Stage | Agent | MCP servers | What Claude does |
|---|---|---|---|
| INGESTED | `ingestion` | corpus-io | calls `ingest_file(source_path, doc_id, doc_type, connector)`, then `save_manifest` with INGESTED stage |
| EXTRACTED | `extraction` | corpus-io | calls `get_chunks(doc_id)`, extracts entities/relations as JSON, calls `save_export(result)`, `save_manifest` with EXTRACTED |
| NORMALIZED | `normalization` | corpus-io, graph-io | calls `get_export(doc_id)`, calls `get_canonical(alias)` per entity, calls `save_export(normalized_result)`, `save_manifest` with NORMALIZED |
| WIKI_COMPILED | `wiki_compiler` | corpus-io, wiki-io | calls `get_export(doc_id)`, reads/creates wiki pages via wiki-io, calls `write_auto_sections`, `save_manifest` with WIKI_COMPILED |
| GRAPH_UPDATED | `graph_curator` | corpus-io, graph-io | calls `merge_by_doc_id(doc_id)`, then `save_manifest` with GRAPH_UPDATED |

---

## New MCP Tools (SP2 additions)

Three new tools needed — all other tool calls use existing SP1 tools.

### 1. `corpus-io.ingest_file`

```python
@app.tool()
async def ingest_file(
    source_path: str,
    doc_id: str,
    doc_type: str,
    source_connector: str,
) -> dict[str, Any]:
    """Ingest a source file: extract text, chunk, embed into Chroma, save JSONL/metadata, update manifest."""
```

Absorbs the full `IngestionAgent` logic:
- Text extraction via pdfplumber (PDF), python-frontmatter (MD), pandas (CSV), plain read otherwise
- Chunking via `chunk_text()` from `llm_rag.utils.chunking`
- Chroma embedding — corpus-io owns a `chromadb.PersistentClient` initialized at server startup
- JSONL chunks saved to `retrieval/chunks/<safe_id>.jsonl`
- Metadata JSON saved to `retrieval/metadata/<safe_id>.json`
- Manifest created or loaded, then updated with INGESTED stage via `save_manifest`
- Returns the updated manifest as a dict

### 2. `corpus-io.get_export`

```python
@app.tool()
async def get_export(doc_id: str) -> dict[str, Any] | None:
    """Read a saved ExtractionResult JSON from graph/exports/. Returns None if not found."""
```

Reads `graph/exports/<safe_id>.json`. Returns the full ExtractionResult as a dict. Used by the normalization and wiki_compiler agents to read what the extraction agent produced.

### 3. `graph-io.merge_by_doc_id`

```python
@app.tool()
async def merge_by_doc_id(doc_id: str) -> None:
    """Merge the normalized extraction result for doc_id into the knowledge graph."""
```

Constructs the normalized export path `graph/exports/<safe_id>.normalized.json` and delegates to the existing `merge_extraction` logic. Removes the need for Claude to construct filesystem paths from doc_id strings.

---

## Async PipelineRunner

### Lifecycle

`PipelineRunner` is an async context manager. The `MCPPool` is entered on `__aenter__` and exits on `__aexit__`. The pool lives for the duration of the supervisor session — one startup, stays alive across all documents.

```python
class PipelineRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pool: MCPPool | None = None

    async def __aenter__(self) -> "PipelineRunner":
        self._pool = MCPPool()
        await self._pool.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._pool is not None:
            await self._pool.__aexit__(*args)

    async def run(self, source_path: Path, force: bool = False) -> DocumentManifest:
        assert self._pool is not None
        manifest = load_manifest(source_path) or create_manifest(...)

        if force or needs_processing(source_path, ProcessingStage.INGESTED):
            await run_agent(INGESTION_AGENT, f"Ingest doc_id={manifest.doc_id} ...", self.settings, self._pool)
            manifest = load_manifest(source_path) or manifest

        if force or needs_processing(source_path, ProcessingStage.EXTRACTED):
            await run_agent(EXTRACTION_AGENT, f"Extract from doc_id={manifest.doc_id}", self.settings, self._pool)
            manifest = load_manifest(source_path) or manifest

        # ... normalization, wiki_compiler, graph_curator same pattern
        return manifest
```

### User message format

Each `run_agent()` call passes a single-line user message with the doc_id and any fields Claude needs to act without reading the manifest itself:

```
"Ingest doc_id=papers/sample-lfp-001, source_path=raw/papers/sample-lfp-001.md, doc_type=papers, source_connector=manual"
"Extract entities and relations from doc_id=papers/sample-lfp-001"
"Normalize entities in doc_id=papers/sample-lfp-001"
"Compile wiki pages for doc_id=papers/sample-lfp-001"
"Update knowledge graph for doc_id=papers/sample-lfp-001"
```

---

## Supervisor Changes

`SupervisorAgent._process_one_node` and `run()` become async. LangGraph graph uses `await graph.ainvoke()`. The `time.sleep()` between iterations becomes `await asyncio.sleep()`. The supervisor receives an already-entered `PipelineRunner` — it does not manage the pool itself.

```python
# supervisor/loop.py
async def _process_one_node(self, state: SupervisorState) -> dict[str, Any]:
    path_str = state["pending_paths"][0]
    try:
        await self.runner.run(Path(path_str))
        ...

async def run(self, max_iterations: int | None = None) -> None:
    self._graph = self._build_graph()
    ...
    result = await self._graph.ainvoke(initial)
    ...
    await asyncio.sleep(self.interval_seconds)
```

CLI entry point (Plan 6) will wrap with `asyncio.run(supervisor.run())`.

---

## Agent Prompt Files

| File | Status | What it instructs |
|---|---|---|
| `agents/prompts/ingestion.md` | **New** | Call `ingest_file(...)` with the doc info from the user message, then confirm INGESTED |
| `agents/prompts/extraction.md` | **Update** | Add: call `get_chunks(doc_id)`, extract JSON, call `save_export`, `save_manifest` with EXTRACTED |
| `agents/prompts/normalization.md` | **Update** | Add: call `get_export`, call `get_canonical` per entity, call `save_export` with normalized result, `save_manifest` with NORMALIZED |
| `agents/prompts/wiki_compiler.md` | **Update** | Add: call `get_export`, use wiki-io tools to read/create/update pages, `save_manifest` with WIKI_COMPILED |
| `agents/prompts/graph_curator.md` | **New** | Call `merge_by_doc_id(doc_id)`, then `save_manifest` with GRAPH_UPDATED |

Prompts describe MCP tools available, expected input (from user message), and the terminal condition (manifest stage updated). They do not contain Python logic.

---

## Testing Strategy

### MCP tool tests (extend `tests/mcp/`)

**`test_corpus_io.py` additions:**
- `test_ingest_file_pdf` — mock pdfplumber, verify chunks JSONL created, manifest INGESTED
- `test_ingest_file_md` — markdown path
- `test_ingest_file_idempotent` — run twice, Chroma delete+re-add, same result
- `test_get_export_found` — reads correct path, returns dict
- `test_get_export_not_found` — returns None

**`test_graph_io.py` additions:**
- `test_merge_by_doc_id` — verify delegates to merge logic with correct normalized path

### Agent definition tests (new `tests/pipeline/test_agents.py`)

Pure unit tests — no API calls:
- Each `AgentDefinition` has the correct model string, MCP server list
- `definition.prompt_path(settings)` resolves to an existing file
- Five tests, one per agent

### PipelineRunner tests (new `tests/pipeline/test_runner.py`)

Mock `run_agent()` to return `""`. Verify:
- Stages run in order for a fresh document
- Stages already in `stages_completed` are skipped
- `force=True` bypasses the manifest gate for all stages
- Runner is usable as async context manager

### Supervisor tests (`tests/supervisor/`)

Update existing sync tests to async (`pytest-asyncio`). `_process_one_node` is now `async def`. Tests use `AsyncMock` for the runner.

### No live API calls

All tests mock `run_agent()`. The single `skipif no ANTHROPIC_API_KEY` smoke test pattern from SP1 is the only exception.

---

## File Layout Summary

**Deleted:**
```
src/llm_rag/pipeline/ingestion.py
src/llm_rag/pipeline/extraction.py
src/llm_rag/pipeline/normalization.py
src/llm_rag/pipeline/wiki_compiler.py
src/llm_rag/pipeline/graph_curator.py
```

**Modified:**
```
src/llm_rag/pipeline/runner.py        — async context manager, five AgentDefinitions, no agent class imports
src/llm_rag/mcp/corpus_io.py          — add ingest_file, get_export tools
src/llm_rag/mcp/graph_io.py           — add merge_by_doc_id tool
src/llm_rag/supervisor/loop.py        — async _process_one_node, async run(), ainvoke
agents/prompts/extraction.md          — update for MCP tool usage
agents/prompts/normalization.md       — update for MCP tool usage
agents/prompts/wiki_compiler.md       — update for MCP tool usage
```

**Created:**
```
agents/prompts/ingestion.md
agents/prompts/graph_curator.md
tests/pipeline/test_agents.py
tests/pipeline/test_runner.py
tests/mcp/test_corpus_io.py           — additions to existing file
tests/mcp/test_graph_io.py            — additions to existing file
```
