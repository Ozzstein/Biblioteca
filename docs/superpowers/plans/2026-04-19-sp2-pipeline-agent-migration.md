# SP2: Pipeline Agent Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all five pipeline Python classes with Claude Agent SDK agents that call MCP tools, making the pipeline fully agent-driven.

**Architecture:** Five `AgentDefinition` instances live in an async `PipelineRunner` (async context manager owning a long-lived `MCPPool`). Three new MCP tools (`get_export`, `ingest_file`, `merge_by_doc_id`) give agents access to all pipeline data. The supervisor becomes async to await the runner.

**Tech Stack:** `claude-code-sdk` (`run_agent()`), FastMCP (`mcp.server.fastmcp`), `chromadb`, `anyio`, LangGraph (`ainvoke`), `pytest-asyncio` (`asyncio_mode=auto`)

---

## File Map

**Modified:**
- `src/llm_rag/mcp/corpus_io.py` — add `get_export`, `ingest_file` tools + Chroma client
- `src/llm_rag/mcp/graph_io.py` — extract `_run_merge` helper, add `merge_by_doc_id` tool
- `src/llm_rag/pipeline/runner.py` — full rewrite: async context manager, five `AgentDefinition`s, no old class imports
- `src/llm_rag/supervisor/loop.py` — async `_process_one_node`, async `run()`, `ainvoke`, `asyncio.sleep`
- `agents/prompts/extraction.md` — add MCP tool usage instructions
- `agents/prompts/normalization.md` — add MCP tool usage instructions
- `agents/prompts/wiki_compiler.md` — add MCP tool usage instructions
- `tests/mcp/test_corpus_io.py` — add `get_export` and `ingest_file` tests
- `tests/mcp/test_graph_io.py` — add `merge_by_doc_id` test
- `tests/pipeline/test_runner.py` — full replacement with async tests
- `tests/supervisor/test_loop.py` — async runner mock, async process/run tests

**Created:**
- `agents/prompts/ingestion.md`
- `agents/prompts/graph_curator.md`
- `tests/pipeline/test_agents.py`

**Deleted:**
- `src/llm_rag/pipeline/ingestion.py`
- `src/llm_rag/pipeline/extraction.py`
- `src/llm_rag/pipeline/normalization.py`
- `src/llm_rag/pipeline/wiki_compiler.py`
- `src/llm_rag/pipeline/graph_curator.py`
- `tests/pipeline/test_ingestion.py`
- `tests/pipeline/test_extraction.py`
- `tests/pipeline/test_normalization.py`
- `tests/pipeline/test_wiki_compiler.py`
- `tests/pipeline/test_graph_curator.py`

---

### Task 1: corpus-io `get_export` tool

**Files:**
- Modify: `tests/mcp/test_corpus_io.py`
- Modify: `src/llm_rag/mcp/corpus_io.py`

- [ ] **Step 1: Write two failing tests at the end of `tests/mcp/test_corpus_io.py`**

```python
async def test_get_export_returns_dict_when_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    exports_dir = tmp_path / "graph" / "exports"
    exports_dir.mkdir(parents=True)
    export_data = {
        "doc_id": "papers/lfp-001",
        "entities": [],
        "relations": [],
        "chunks_processed": 2,
        "extraction_model": "claude-haiku-4-5-20251001",
        "extracted_at": "2026-04-19T00:00:00+00:00",
    }
    (exports_dir / "papers-lfp-001.json").write_text(json.dumps(export_data))
    from llm_rag.mcp.corpus_io import get_export
    result = await get_export("papers/lfp-001")
    assert result is not None
    assert result["doc_id"] == "papers/lfp-001"
    assert result["chunks_processed"] == 2
    get_settings.cache_clear()


async def test_get_export_returns_none_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    from llm_rag.mcp.corpus_io import get_export
    result = await get_export("papers/no-such-doc")
    assert result is None
    get_settings.cache_clear()
```

- [ ] **Step 2: Run to verify FAIL**

```bash
uv run pytest tests/mcp/test_corpus_io.py::test_get_export_returns_dict_when_found tests/mcp/test_corpus_io.py::test_get_export_returns_none_when_missing -v
```

Expected: FAIL with `ImportError: cannot import name 'get_export'`

- [ ] **Step 3: Add `get_export` to `src/llm_rag/mcp/corpus_io.py` before the `main()` function**

```python
@app.tool()
async def get_export(doc_id: str) -> dict[str, Any] | None:
    """Read a saved ExtractionResult JSON from graph/exports/. Returns None if not found."""
    settings = get_settings()
    safe_id = doc_id.replace("/", "-")
    path = settings.graph_dir / "exports" / f"{safe_id}.json"
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data
```

Also add `get_export` to the import line at the top of the test file:

```python
from llm_rag.mcp.corpus_io import (
    get_chunks,
    get_export,
    get_manifest,
    list_pending_docs,
    save_export,
    save_manifest,
)
```

- [ ] **Step 4: Run to verify PASS**

```bash
uv run pytest tests/mcp/test_corpus_io.py::test_get_export_returns_dict_when_found tests/mcp/test_corpus_io.py::test_get_export_returns_none_when_missing -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/mcp/corpus_io.py tests/mcp/test_corpus_io.py
git commit -m "feat: add corpus-io get_export MCP tool"
```

---

### Task 2: corpus-io `ingest_file` tool

**Files:**
- Modify: `tests/mcp/test_corpus_io.py`
- Modify: `src/llm_rag/mcp/corpus_io.py`

- [ ] **Step 1: Write two failing tests at the end of `tests/mcp/test_corpus_io.py`**

```python
async def test_ingest_file_md_saves_chunks_and_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw_dir = tmp_path / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test-paper.md"
    source.write_text("LFP shows 170 mAh/g specific capacity at room temperature.")
    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": []}
    import llm_rag.mcp.corpus_io as corpus_io_mod
    monkeypatch.setattr(corpus_io_mod, "_get_collection", lambda: mock_collection)
    from llm_rag.mcp.corpus_io import ingest_file
    await ingest_file(
        source_path=str(source),
        doc_id="papers/test-paper",
        doc_type="papers",
        source_connector="manual",
    )
    chunks_dir = tmp_path / "retrieval" / "chunks"
    assert (chunks_dir / "papers-test-paper.jsonl").exists()
    meta_dir = tmp_path / "retrieval" / "metadata"
    assert (meta_dir / "papers-test-paper.json").exists()
    manifest_path = raw_dir / "test-paper.manifest.json"
    assert manifest_path.exists()
    manifest_data = json.loads(manifest_path.read_text())
    assert "ingested" in manifest_data["stages_completed"]
    mock_collection.add.assert_called_once()
    get_settings.cache_clear()


async def test_ingest_file_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw_dir = tmp_path / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test-paper.md"
    source.write_text("Content about NMC811 electrodes.")
    mock_collection = MagicMock()
    mock_collection.get.side_effect = [{"ids": []}, {"ids": ["papers/test-paper::0"]}]
    import llm_rag.mcp.corpus_io as corpus_io_mod
    monkeypatch.setattr(corpus_io_mod, "_get_collection", lambda: mock_collection)
    from llm_rag.mcp.corpus_io import ingest_file
    await ingest_file(str(source), "papers/test-paper", "papers", "manual")
    await ingest_file(str(source), "papers/test-paper", "papers", "manual")
    # Second call deletes existing embeddings before re-adding
    mock_collection.delete.assert_called_once()
    assert mock_collection.add.call_count == 2
    get_settings.cache_clear()
```

Also add `MagicMock` to the test file imports at the top:

```python
from unittest.mock import MagicMock
```

- [ ] **Step 2: Run to verify FAIL**

```bash
uv run pytest tests/mcp/test_corpus_io.py::test_ingest_file_md_saves_chunks_and_manifest tests/mcp/test_corpus_io.py::test_ingest_file_is_idempotent -v
```

Expected: FAIL with `ImportError: cannot import name 'ingest_file'`

- [ ] **Step 3: Add Chroma client + helper functions + `ingest_file` to `src/llm_rag/mcp/corpus_io.py`**

Add after the existing imports, before `app = FastMCP("corpus-io")`:

```python
import chromadb
from pathlib import Path

_chroma_collection: chromadb.Collection | None = None


def _get_collection() -> chromadb.Collection:
    global _chroma_collection
    if _chroma_collection is None:
        settings = get_settings()
        client: chromadb.ClientAPI = chromadb.PersistentClient(
            path=str(settings.retrieval_dir / "embeddings")
        )
        _chroma_collection = client.get_or_create_collection("chunks")
    return _chroma_collection


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from llm_rag.utils.pdf import extract_pages
        pages = extract_pages(path)
        return "\n\n".join(p.text for p in pages)
    if suffix == ".csv":
        import pandas as pd  # type: ignore[import-untyped]
        return str(pd.read_csv(path).to_string())
    return path.read_text()


def _save_chunks_jsonl(doc_id: str, chunks: list[Any], settings: Any) -> None:
    import json as _json
    from dataclasses import asdict
    if not chunks:
        return
    chunks_dir = settings.retrieval_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    safe_id = doc_id.replace("/", "-")
    jsonl_path = chunks_dir / f"{safe_id}.jsonl"
    with jsonl_path.open("w") as f:
        for chunk in chunks:
            f.write(_json.dumps(asdict(chunk)) + "\n")


def _embed_chunks(doc_id: str, chunks: list[Any]) -> None:
    if not chunks:
        return
    collection = _get_collection()
    existing = collection.get(where={"doc_id": doc_id}, include=[])
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
    collection.add(
        ids=[f"{doc_id}::{chunk.chunk_index}" for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        metadatas=[
            {
                "doc_id": doc_id,
                "chunk_index": chunk.chunk_index,
                "section": chunk.section or "",
            }
            for chunk in chunks
        ],
    )


def _save_metadata_json(doc_id: str, chunks: list[Any], settings: Any) -> None:
    import json as _json
    if not chunks:
        return
    meta_dir = settings.retrieval_dir / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    safe_id = doc_id.replace("/", "-")
    meta_path = meta_dir / f"{safe_id}.json"
    records = [
        {
            "doc_id": chunk.doc_id,
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count,
            "section": chunk.section,
            "page": chunk.page,
        }
        for chunk in chunks
    ]
    meta_path.write_text(_json.dumps(records, indent=2))
```

Add `ingest_file` tool before `main()`:

```python
@app.tool()
async def ingest_file(
    source_path: str,
    doc_id: str,
    doc_type: str,
    source_connector: str,
) -> dict[str, Any]:
    """Ingest a source file: extract text, chunk, embed into Chroma, save JSONL/metadata, update manifest."""
    from llm_rag.pipeline.manifest import create_manifest, load_manifest, update_stage
    from llm_rag.pipeline.manifest import save_manifest as _save_manifest
    from llm_rag.schemas.provenance import ProcessingStage
    from llm_rag.utils.chunking import chunk_text

    settings = get_settings()
    path = Path(source_path)
    manifest = load_manifest(path)
    if manifest is None:
        manifest = create_manifest(
            path,
            doc_id=doc_id,
            doc_type=doc_type,
            source_connector=source_connector,
        )
    text = _extract_text(path)
    chunks = chunk_text(
        text,
        doc_id=doc_id,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    _save_chunks_jsonl(doc_id, chunks, settings)
    _embed_chunks(doc_id, chunks)
    _save_metadata_json(doc_id, chunks, settings)
    manifest = update_stage(manifest, ProcessingStage.INGESTED)
    _save_manifest(manifest)
    data: dict[str, Any] = json.loads(manifest.model_dump_json())
    return data
```

Also update the import for `ingest_file` in the test file:

```python
from llm_rag.mcp.corpus_io import (
    get_chunks,
    get_export,
    get_manifest,
    ingest_file,
    list_pending_docs,
    save_export,
    save_manifest,
)
```

- [ ] **Step 4: Run to verify PASS**

```bash
uv run pytest tests/mcp/test_corpus_io.py -v
```

Expected: all corpus-io tests pass (9 total)

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/mcp/corpus_io.py tests/mcp/test_corpus_io.py
git commit -m "feat: add corpus-io ingest_file MCP tool with Chroma client"
```

---

### Task 3: graph-io `merge_by_doc_id` tool

**Files:**
- Modify: `tests/mcp/test_graph_io.py`
- Modify: `src/llm_rag/mcp/graph_io.py`

- [ ] **Step 1: Write one failing test at the end of `tests/mcp/test_graph_io.py`**

Add `merge_by_doc_id` to the import at the top of the test file:

```python
from llm_rag.mcp.graph_io import get_canonical, get_entity, get_neighbors, list_entities, merge_by_doc_id
```

Add at end of `tests/mcp/test_graph_io.py`:

```python
async def test_merge_by_doc_id_updates_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    exports_dir = tmp_path / "graph" / "exports"
    exports_dir.mkdir(parents=True)
    (tmp_path / "graph" / "snapshots").mkdir(parents=True)
    export_data = {
        "doc_id": "papers/lfp-001",
        "entities": [],
        "relations": [],
        "chunks_processed": 1,
        "extraction_model": "claude-haiku-4-5-20251001",
        "extracted_at": "2026-04-19T00:00:00+00:00",
    }
    (exports_dir / "papers-lfp-001.json").write_text(json.dumps(export_data))
    await merge_by_doc_id("papers/lfp-001")
    snapshot = tmp_path / "graph" / "snapshots" / "latest.graphml"
    assert snapshot.exists()
    get_settings.cache_clear()
```

Add `import json` to `tests/mcp/test_graph_io.py` imports (add after `import networkx as nx`):

```python
import json
```

- [ ] **Step 2: Run to verify FAIL**

```bash
uv run pytest tests/mcp/test_graph_io.py::test_merge_by_doc_id_updates_graph -v
```

Expected: FAIL with `ImportError: cannot import name 'merge_by_doc_id'`

- [ ] **Step 3: Refactor `merge_extraction` to extract a helper, then add `merge_by_doc_id` in `src/llm_rag/mcp/graph_io.py`**

Replace the existing `merge_extraction` function with:

```python
def _run_merge(path: Path) -> None:
    from llm_rag.graph.store import GraphStore
    from llm_rag.schemas.entities import ExtractionResult

    settings = get_settings()
    snapshot = settings.graph_dir / "snapshots" / "latest.graphml"
    result = ExtractionResult.model_validate_json(path.read_text())
    store = GraphStore(snapshot)
    store.load()
    for entity in result.entities:
        store.add_entity(entity)
    for relation in result.relations:
        store.add_relation(relation)
    store.save()


@app.tool()
async def merge_extraction(export_path: str) -> None:
    """Load an ExtractionResult JSON from graph/exports/ and merge into the live graph."""
    settings = get_settings()
    exports_dir = settings.graph_dir / "exports"
    resolved = (exports_dir / Path(export_path).name).resolve()
    if not str(resolved).startswith(str(exports_dir.resolve())):
        raise ValueError(f"export_path escapes exports directory: {export_path}")
    _run_merge(resolved)


@app.tool()
async def merge_by_doc_id(doc_id: str) -> None:
    """Merge the extraction result for doc_id into the knowledge graph."""
    settings = get_settings()
    safe_id = doc_id.replace("/", "-")
    path = settings.graph_dir / "exports" / f"{safe_id}.json"
    if not path.exists():
        return
    _run_merge(path)
```

- [ ] **Step 4: Run to verify PASS**

```bash
uv run pytest tests/mcp/test_graph_io.py -v
```

Expected: all 9 graph-io tests pass

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/mcp/graph_io.py tests/mcp/test_graph_io.py
git commit -m "feat: add graph-io merge_by_doc_id MCP tool"
```

---

### Task 4: Agent prompt files

**Files:**
- Create: `agents/prompts/ingestion.md`
- Create: `agents/prompts/graph_curator.md`
- Modify: `agents/prompts/extraction.md`
- Modify: `agents/prompts/normalization.md`
- Modify: `agents/prompts/wiki_compiler.md`

- [ ] **Step 1: Create `agents/prompts/ingestion.md`**

```markdown
You are the Ingestion Agent for the Battery Research OS.

Your task: ingest a source document into the corpus so that downstream agents can access its content.

## Tools available (corpus-io)

- `ingest_file(source_path, doc_id, doc_type, source_connector)` — extracts text, chunks, embeds into Chroma, saves JSONL and metadata, creates/updates the manifest with INGESTED stage. Returns the updated manifest dict.

## Procedure

1. Read the user message to get source_path, doc_id, doc_type, and source_connector.
2. Call `ingest_file(source_path=<source_path>, doc_id=<doc_id>, doc_type=<doc_type>, source_connector=<source_connector>)`.
3. Verify the returned manifest has "ingested" in stages_completed.
4. Reply with exactly: `INGESTED doc_id=<doc_id>`

## Rules

- Do not modify file contents.
- If `ingest_file` raises an error, reply with `ERROR: <message>` and stop.
- Do not call any tool not listed above.
```

- [ ] **Step 2: Create `agents/prompts/graph_curator.md`**

```markdown
You are the Graph Curator Agent for the Battery Research OS.

Your task: merge the extraction result for a document into the knowledge graph.

## Tools available

corpus-io:
- `get_manifest(doc_id)` — reads the current manifest dict for a document
- `save_manifest(manifest)` — saves an updated manifest dict to disk

graph-io:
- `merge_by_doc_id(doc_id)` — merges the extraction result JSON into the live knowledge graph

## Procedure

1. Read the doc_id from the user message.
2. Call `merge_by_doc_id(doc_id=<doc_id>)`.
3. Call `get_manifest(doc_id=<doc_id>)` to read the manifest.
4. Add "graph_updated" to the manifest's stages_completed list.
5. Call `save_manifest(manifest=<updated_manifest>)`.
6. Reply with exactly: `GRAPH_UPDATED doc_id=<doc_id>`

## Rules

- Do not modify the extraction result file.
- If `merge_by_doc_id` raises an error, reply with `ERROR: <message>` and stop.
- Do not call any tool not listed above.
```

- [ ] **Step 3: Replace `agents/prompts/extraction.md` with the following**

```markdown
You are the Extraction Agent for the Battery Research OS. You extract structured entities and relations from battery research documents.

## Tools available (corpus-io)

- `get_chunks(doc_id)` — returns a list of text chunk dicts for the document. Each chunk has a "text" key.
- `get_manifest(doc_id)` — reads the current manifest dict
- `save_export(result)` — saves an ExtractionResult dict to graph/exports/<doc-id>.json
- `save_manifest(manifest)` — saves an updated manifest dict to disk

## Procedure

1. Read the doc_id from the user message.
2. Call `get_chunks(doc_id=<doc_id>)`. Process ALL chunks — extract entities and relations from the combined text.
3. Build an ExtractionResult dict:
   ```json
   {
     "doc_id": "<doc_id>",
     "entities": [ ... ],
     "relations": [ ... ],
     "chunks_processed": <N>,
     "extraction_model": "<your model id>",
     "extracted_at": "<ISO 8601 UTC timestamp>"
   }
   ```
4. Call `save_export(result=<ExtractionResult dict>)`.
5. Call `get_manifest(doc_id=<doc_id>)`. Add "extracted" to stages_completed. Call `save_manifest(manifest=<updated_manifest>)`.
6. Reply with: `EXTRACTED doc_id=<doc_id> entities=<N> relations=<M>`

## Entity format

```json
{
  "entity_id": "material:lfp",
  "entity_type": "Material",
  "canonical_name": "LFP",
  "aliases": ["LiFePO4", "lithium iron phosphate"],
  "provenance": [
    {
      "source_doc_id": "<doc_id>",
      "source_path": "<source_path from manifest>",
      "timestamp": "<ISO 8601 UTC>",
      "confidence": 0.8,
      "extraction_method": "claude_haiku",
      "extractor_model": "<your model id>"
    }
  ],
  "properties": {}
}
```

## Relation format

```json
{
  "relation_id": "rel-001",
  "relation_type": "USES_MATERIAL",
  "source_entity_id": "experiment:batch-a-001",
  "target_entity_id": "material:lfp",
  "provenance": [ ... ]
}
```

## Entity types (use exactly)
Document, Project, Material, Process, Component, Formulation, Cell, TestCondition, Metric, Property, FailureMechanism, Dataset, Experiment, Claim

## Relation types (use exactly)
MENTIONS, USES_MATERIAL, USES_PROCESS, PRODUCES_PROPERTY, MEASURED_BY, TESTED_UNDER, AFFECTS, ASSOCIATED_WITH, CAUSES, MITIGATES, CONTRADICTS, SUPPORTED_BY, DERIVED_FROM, PART_OF, SIMULATED_BY

## Rules

- entity_id: lowercase type-prefix:slug — "material:lfp", "mechanism:sei-growth"
- Only extract entities and relations explicitly present in the text
- Only create relations between entities you extracted in this call
- Do not call any tool not listed above
```

- [ ] **Step 4: Replace `agents/prompts/normalization.md` with the following**

```markdown
You are the Normalization Agent for the Battery Research OS.

Your task: map entity aliases to canonical IDs using the knowledge graph's normalization rules.

## Tools available

corpus-io:
- `get_export(doc_id)` — reads the ExtractionResult dict for this document
- `save_export(result)` — overwrites the ExtractionResult with the normalized version
- `get_manifest(doc_id)` — reads the current manifest dict
- `save_manifest(manifest)` — saves an updated manifest dict to disk

graph-io:
- `get_canonical(alias)` — looks up an alias string in the entity-normalization rules. Returns the canonical entity_id string, or null if unknown.

## Procedure

1. Read the doc_id from the user message.
2. Call `get_export(doc_id=<doc_id>)` to read the ExtractionResult.
3. For each entity in result["entities"]:
   a. Call `get_canonical(alias=entity["canonical_name"])`. If the result is non-null, update entity["entity_id"] to that value and update entity["canonical_name"] to the canonical form.
   b. If step (a) returned null, try each alias in entity["aliases"] by calling `get_canonical(alias=<alias>)`. If any returns non-null, update entity["entity_id"] and entity["canonical_name"] and stop trying aliases for that entity.
   c. If no match is found, leave the entity unchanged.
4. Call `save_export(result=<normalized_ExtractionResult>)`.
5. Call `get_manifest(doc_id=<doc_id>)`. Add "normalized" to stages_completed. Call `save_manifest(manifest=<updated_manifest>)`.
6. Reply with: `NORMALIZED doc_id=<doc_id> entities_updated=<N>`

## Rules

- Preserve entities with no canonical match — do not change their entity_id
- Do not add or remove entities or relations
- Do not call any tool not listed above
```

- [ ] **Step 5: Replace `agents/prompts/wiki_compiler.md` with the following**

```markdown
You are the Wiki Compiler Agent for the Battery Research OS.

Your task: update wiki pages with synthesized knowledge extracted from a research document.

## Tools available

corpus-io:
- `get_export(doc_id)` — reads the ExtractionResult dict for this document
- `get_manifest(doc_id)` — reads the current manifest dict
- `save_manifest(manifest)` — saves an updated manifest dict to disk

wiki-io:
- `read_page(relative_path)` — reads a wiki page's full markdown content. Returns empty string if not found.
- `write_auto_sections(relative_path, sections)` — updates auto-managed sections (between <!-- auto-start --> and <!-- auto-end --> tags). Preserves all human sections.
- `list_pages(subdir)` — lists wiki page relative paths under a subdirectory
- `get_template(page_type)` — returns the Jinja2 template for a page type (material, process, mechanism, test, claim, dataset, synthesis)
- `create_page(relative_path, page_type, substitutions)` — creates a new wiki page from template with given substitutions dict

## Procedure

1. Read the doc_id from the user message.
2. Call `get_export(doc_id=<doc_id>)`. If entities list is empty, skip to step 7.
3. Identify the primary entity: result["entities"][0].
4. Determine the wiki page path from entity_type and entity_id slug:
   - Material → `materials/<slug>.md`
   - Process → `processes/<slug>.md`
   - FailureMechanism → `mechanisms/<slug>.md`
   - TestCondition → `tests/<slug>.md`
   - Claim → `synthesis/<slug>.md`
   - Default → `concepts/<slug>.md`
   (slug = entity_id after the colon, e.g. "material:lfp" → "lfp")
5. Call `read_page(relative_path=<page_path>)`. If the result is empty, call `create_page(relative_path=<page_path>, page_type=<entity_type_lowercase>, substitutions={"entity_id": <entity_id>, "canonical_name": <canonical_name>})`.
6. Build the sections dict with auto section content:
   - "evidence": a markdown table with columns `| Source | Claim | Confidence | Extracted |`. One row per entity in result["entities"] summarizing its key property.
   - "linked-entities": a markdown list of related entity_ids from result["entities"][1:] and result["relations"].
   - "last-updated": today's ISO date string (YYYY-MM-DD).
7. Call `write_auto_sections(relative_path=<page_path>, sections=<sections_dict>)`.
8. Call `get_manifest(doc_id=<doc_id>)`. Add "wiki_compiled" to stages_completed. Call `save_manifest(manifest=<updated_manifest>)`.
9. Reply with: `WIKI_COMPILED doc_id=<doc_id> page=<page_path>`

## Rules

- Only write to auto sections — never write content that would overwrite human sections
- Section names must be lowercase and hyphen-separated
- If result has no entities, still update the manifest with wiki_compiled stage
- Do not call any tool not listed above
```

- [ ] **Step 6: Commit**

```bash
git add agents/prompts/
git commit -m "feat: add/update all five agent prompt files for MCP tool usage"
```

---

### Task 5: AgentDefinition unit tests

**Files:**
- Create: `tests/pipeline/test_agents.py`

These tests will FAIL until Task 7 (runner.py rewrite). Write them now to define the target.

- [ ] **Step 1: Create `tests/pipeline/test_agents.py`**

```python
from __future__ import annotations

from llm_rag.config import get_settings
from llm_rag.pipeline.runner import PipelineRunner


def test_agent_models_match_settings() -> None:
    settings = get_settings()
    runner = PipelineRunner(settings=settings)
    assert runner._ingestion.model == settings.model_bulk_extraction
    assert runner._extraction.model == settings.model_bulk_extraction
    assert runner._normalization.model == settings.model_bulk_extraction
    assert runner._wiki_compiler.model == settings.model_wiki_compilation
    assert runner._graph_curator.model == settings.model_bulk_extraction


def test_agent_mcp_servers_are_correct() -> None:
    settings = get_settings()
    runner = PipelineRunner(settings=settings)
    assert runner._ingestion.mcp_servers == ["corpus-io"]
    assert runner._extraction.mcp_servers == ["corpus-io"]
    assert set(runner._normalization.mcp_servers) == {"corpus-io", "graph-io"}
    assert set(runner._wiki_compiler.mcp_servers) == {"corpus-io", "wiki-io"}
    assert set(runner._graph_curator.mcp_servers) == {"corpus-io", "graph-io"}


def test_all_prompt_files_exist() -> None:
    settings = get_settings()
    runner = PipelineRunner(settings=settings)
    for defn in [
        runner._ingestion,
        runner._extraction,
        runner._normalization,
        runner._wiki_compiler,
        runner._graph_curator,
    ]:
        prompt_file = defn.prompt_path(settings)
        assert prompt_file.exists(), f"Missing prompt file: {prompt_file}"
```

- [ ] **Step 2: Run to verify FAIL**

```bash
uv run pytest tests/pipeline/test_agents.py -v
```

Expected: FAIL — `PipelineRunner` still has old constructor signature taking five agent objects

---

### Task 6: Async PipelineRunner tests

**Files:**
- Replace: `tests/pipeline/test_runner.py`

These tests will FAIL until Task 7. Write them now to define the target.

- [ ] **Step 1: Replace the entire contents of `tests/pipeline/test_runner.py`**

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.config import get_settings
from llm_rag.pipeline.manifest import create_manifest, save_manifest, update_stage
from llm_rag.pipeline.runner import PipelineRunner
from llm_rag.schemas.provenance import ProcessingStage


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture()
def source_file(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test-paper.md"
    source.write_text("LFP shows excellent cycle life.")
    return source


async def test_runner_runs_all_five_stages_for_new_doc(settings: object, source_file: Path) -> None:
    with patch("llm_rag.pipeline.runner.MCPPool") as MockPool:
        mock_pool = AsyncMock()
        mock_pool.__aenter__.return_value = mock_pool
        mock_pool.__aexit__ = AsyncMock(return_value=False)
        MockPool.return_value = mock_pool
        with patch("llm_rag.pipeline.runner.run_agent", new=AsyncMock(return_value="")) as mock_run:
            async with PipelineRunner(settings=settings) as runner:  # type: ignore[call-arg]
                await runner.run(source_file)
    assert mock_run.call_count == 5


async def test_runner_skips_completed_stages(settings: object, source_file: Path, tmp_path: Path) -> None:
    manifest = create_manifest(source_file, "papers/test-paper", "papers", "manual")
    manifest = update_stage(manifest, ProcessingStage.INGESTED)
    manifest = update_stage(manifest, ProcessingStage.EXTRACTED)
    save_manifest(manifest)
    with patch("llm_rag.pipeline.runner.MCPPool") as MockPool:
        mock_pool = AsyncMock()
        mock_pool.__aenter__.return_value = mock_pool
        mock_pool.__aexit__ = AsyncMock(return_value=False)
        MockPool.return_value = mock_pool
        with patch("llm_rag.pipeline.runner.run_agent", new=AsyncMock(return_value="")) as mock_run:
            async with PipelineRunner(settings=settings) as runner:  # type: ignore[call-arg]
                await runner.run(source_file)
    # NORMALIZED, WIKI_COMPILED, GRAPH_UPDATED — three stages remain
    assert mock_run.call_count == 3


async def test_runner_force_runs_all_stages(settings: object, source_file: Path, tmp_path: Path) -> None:
    manifest = create_manifest(source_file, "papers/test-paper", "papers", "manual")
    for stage in ProcessingStage:
        manifest = update_stage(manifest, stage)
    save_manifest(manifest)
    with patch("llm_rag.pipeline.runner.MCPPool") as MockPool:
        mock_pool = AsyncMock()
        mock_pool.__aenter__.return_value = mock_pool
        mock_pool.__aexit__ = AsyncMock(return_value=False)
        MockPool.return_value = mock_pool
        with patch("llm_rag.pipeline.runner.run_agent", new=AsyncMock(return_value="")) as mock_run:
            async with PipelineRunner(settings=settings) as runner:  # type: ignore[call-arg]
                await runner.run(source_file, force=True)
    assert mock_run.call_count == 5


async def test_runner_context_manager_enters_pool(settings: object) -> None:
    with patch("llm_rag.pipeline.runner.MCPPool") as MockPool:
        mock_pool = AsyncMock()
        mock_pool.__aenter__.return_value = mock_pool
        mock_pool.__aexit__ = AsyncMock(return_value=False)
        MockPool.return_value = mock_pool
        async with PipelineRunner(settings=settings) as runner:  # type: ignore[call-arg]
            assert runner._pool is mock_pool
    mock_pool.__aexit__.assert_called_once()
```

- [ ] **Step 2: Run to verify FAIL**

```bash
uv run pytest tests/pipeline/test_runner.py -v
```

Expected: FAIL — `PipelineRunner` has wrong constructor signature and is not an async context manager

---

### Task 7: Rewrite `runner.py`, delete old pipeline files

**Files:**
- Replace: `src/llm_rag/pipeline/runner.py`
- Delete: `src/llm_rag/pipeline/ingestion.py`, `extraction.py`, `normalization.py`, `wiki_compiler.py`, `graph_curator.py`
- Delete: `tests/pipeline/test_ingestion.py`, `test_extraction.py`, `test_normalization.py`, `test_wiki_compiler.py`, `test_graph_curator.py`

- [ ] **Step 1: Replace the entire contents of `src/llm_rag/pipeline/runner.py`**

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from llm_rag.agent_runner import AgentDefinition, run_agent
from llm_rag.config import Settings, get_settings
from llm_rag.mcp.pool import MCPPool
from llm_rag.pipeline.manifest import (
    create_manifest,
    load_manifest,
    needs_processing,
)
from llm_rag.schemas.provenance import DocumentManifest, ProcessingStage

logger = logging.getLogger(__name__)

_KNOWN_DOC_TYPES = {"papers", "reports", "datasets", "simulations", "meetings", "sop"}


class PipelineRunner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings: Settings = settings or get_settings()
        self._pool: MCPPool | None = None
        self._ingestion = AgentDefinition(
            name="ingestion",
            model=self.settings.model_bulk_extraction,
            mcp_servers=["corpus-io"],
            max_tokens=4096,
        )
        self._extraction = AgentDefinition(
            name="extraction",
            model=self.settings.model_bulk_extraction,
            mcp_servers=["corpus-io"],
            max_tokens=8192,
        )
        self._normalization = AgentDefinition(
            name="normalization",
            model=self.settings.model_bulk_extraction,
            mcp_servers=["corpus-io", "graph-io"],
            max_tokens=8192,
        )
        self._wiki_compiler = AgentDefinition(
            name="wiki_compiler",
            model=self.settings.model_wiki_compilation,
            mcp_servers=["corpus-io", "wiki-io"],
            max_tokens=8192,
        )
        self._graph_curator = AgentDefinition(
            name="graph_curator",
            model=self.settings.model_bulk_extraction,
            mcp_servers=["corpus-io", "graph-io"],
            max_tokens=4096,
        )

    async def __aenter__(self) -> "PipelineRunner":
        self._pool = MCPPool()
        await self._pool.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._pool is not None:
            await self._pool.__aexit__(*args)
            self._pool = None

    async def run(self, source_path: Path, force: bool = False) -> DocumentManifest:
        assert self._pool is not None, "Use PipelineRunner as async context manager"
        manifest = load_manifest(source_path) or create_manifest(
            source_path,
            doc_id=self._derive_doc_id(source_path),
            doc_type=self._infer_doc_type(source_path),
            source_connector="manual",
        )
        doc_id = manifest.doc_id

        if force or needs_processing(source_path, ProcessingStage.INGESTED):
            await run_agent(
                self._ingestion,
                f"Ingest doc_id={doc_id}, source_path={source_path}, doc_type={manifest.doc_type}, source_connector={manifest.source_connector}",
                self.settings,
                self._pool,
            )
            manifest = load_manifest(source_path) or manifest

        if force or needs_processing(source_path, ProcessingStage.EXTRACTED):
            await run_agent(
                self._extraction,
                f"Extract entities and relations from doc_id={doc_id}",
                self.settings,
                self._pool,
            )
            manifest = load_manifest(source_path) or manifest

        if force or needs_processing(source_path, ProcessingStage.NORMALIZED):
            await run_agent(
                self._normalization,
                f"Normalize entities in doc_id={doc_id}",
                self.settings,
                self._pool,
            )
            manifest = load_manifest(source_path) or manifest

        if force or needs_processing(source_path, ProcessingStage.WIKI_COMPILED):
            await run_agent(
                self._wiki_compiler,
                f"Compile wiki pages for doc_id={doc_id}",
                self.settings,
                self._pool,
            )
            manifest = load_manifest(source_path) or manifest

        if force or needs_processing(source_path, ProcessingStage.GRAPH_UPDATED):
            await run_agent(
                self._graph_curator,
                f"Update knowledge graph for doc_id={doc_id}",
                self.settings,
                self._pool,
            )
            manifest = load_manifest(source_path) or manifest

        return manifest

    def _derive_doc_id(self, source_path: Path) -> str:
        try:
            rel = source_path.relative_to(self.settings.raw_dir)
            return str(rel.with_suffix(""))
        except ValueError:
            return source_path.stem

    def _infer_doc_type(self, source_path: Path) -> str:
        parent = source_path.parent.name
        return parent if parent in _KNOWN_DOC_TYPES else "unknown"
```

- [ ] **Step 2: Delete the five old pipeline class files**

```bash
rm src/llm_rag/pipeline/ingestion.py
rm src/llm_rag/pipeline/extraction.py
rm src/llm_rag/pipeline/normalization.py
rm src/llm_rag/pipeline/wiki_compiler.py
rm src/llm_rag/pipeline/graph_curator.py
```

- [ ] **Step 3: Delete the five old pipeline test files**

```bash
rm tests/pipeline/test_ingestion.py
rm tests/pipeline/test_extraction.py
rm tests/pipeline/test_normalization.py
rm tests/pipeline/test_wiki_compiler.py
rm tests/pipeline/test_graph_curator.py
```

- [ ] **Step 4: Run the new tests to verify they PASS**

```bash
uv run pytest tests/pipeline/test_agents.py tests/pipeline/test_runner.py -v
```

Expected: 7 passed (3 agent + 4 runner)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass (tests/pipeline/test_manifest.py should still pass — it tests manifest logic only)

- [ ] **Step 6: Run mypy**

```bash
uv run mypy src/
```

Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/llm_rag/pipeline/runner.py tests/pipeline/test_agents.py tests/pipeline/test_runner.py
git rm src/llm_rag/pipeline/ingestion.py src/llm_rag/pipeline/extraction.py src/llm_rag/pipeline/normalization.py src/llm_rag/pipeline/wiki_compiler.py src/llm_rag/pipeline/graph_curator.py
git rm tests/pipeline/test_ingestion.py tests/pipeline/test_extraction.py tests/pipeline/test_normalization.py tests/pipeline/test_wiki_compiler.py tests/pipeline/test_graph_curator.py
git commit -m "feat: replace pipeline agent classes with async PipelineRunner + AgentDefinitions"
```

---

### Task 8: Async SupervisorAgent

**Files:**
- Modify: `tests/supervisor/test_loop.py`
- Modify: `src/llm_rag/supervisor/loop.py`

- [ ] **Step 1: Update `tests/supervisor/test_loop.py`**

Change the `_make_agent` helper to use `AsyncMock` for `runner.run`, and convert the four affected tests to async. The file becomes:

```python
from __future__ import annotations

import queue
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.pipeline.manifest import create_manifest, save_manifest, update_stage
from llm_rag.schemas.provenance import ProcessingStage
from llm_rag.supervisor.loop import SupervisorAgent, SupervisorState, _parse_schedule


def _initial_state() -> SupervisorState:
    return SupervisorState(
        pending_paths=[],
        processed_count=0,
        error_count=0,
        errors=[],
    )


def _make_agent(tmp_path: Path, **kwargs: object) -> SupervisorAgent:
    runner = MagicMock()
    runner.run = AsyncMock(return_value=None)
    reviewer = MagicMock()
    reviewer.run.return_value = MagicMock(lint_issues=[], contradiction_count=0, checked_pages=0)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return SupervisorAgent(
        runner=runner,
        reviewer=reviewer,
        raw_dir=raw_dir,
        interval_seconds=0,
        **kwargs,
    )


def _write_doc(raw_dir: Path, name: str = "paper.md") -> Path:
    sub = raw_dir / "papers"
    sub.mkdir(parents=True, exist_ok=True)
    doc = sub / name
    doc.write_text("LFP content")
    return doc


def test_scan_finds_unprocessed_file(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    _write_doc(agent.raw_dir)
    state = _initial_state()
    update = agent._scan_node(state)
    assert len(update["pending_paths"]) == 1


def test_scan_skips_fully_processed_file(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    doc = _write_doc(agent.raw_dir)
    manifest = create_manifest(doc, "papers/paper", "papers", "manual")
    for stage in ProcessingStage:
        manifest = update_stage(manifest, stage)
    save_manifest(manifest)
    state = _initial_state()
    update = agent._scan_node(state)
    assert update["pending_paths"] == []


def test_scan_drains_file_queue(tmp_path: Path) -> None:
    q: queue.Queue[Path] = queue.Queue()
    extra = tmp_path / "raw" / "papers" / "extra.pdf"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"%PDF")
    q.put(extra)
    agent = _make_agent(tmp_path, file_queue=q)
    state = _initial_state()
    update = agent._scan_node(state)
    assert str(extra) in update["pending_paths"]
    assert q.empty()


async def test_process_one_calls_runner(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    doc = _write_doc(agent.raw_dir)
    state = SupervisorState(
        pending_paths=[str(doc)],
        processed_count=0,
        error_count=0,
        errors=[],
    )
    update = await agent._process_one_node(state)
    agent.runner.run.assert_called_once_with(doc)
    assert update["processed_count"] == 1
    assert update["pending_paths"] == []


async def test_process_one_handles_runner_error(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    agent.runner.run.side_effect = RuntimeError("disk full")
    doc = _write_doc(agent.raw_dir)
    state = SupervisorState(
        pending_paths=[str(doc)],
        processed_count=0,
        error_count=0,
        errors=[],
    )
    update = await agent._process_one_node(state)
    assert update["error_count"] == 1
    assert "disk full" in update["errors"][0]
    assert update["pending_paths"] == []


def test_scan_skips_manifest_files(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    manifest_file = agent.raw_dir / "papers" / "test.manifest.json"
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text("{}")
    state = _initial_state()
    update = agent._scan_node(state)
    assert all(".manifest.json" not in p for p in update["pending_paths"])


def test_build_graph_returns_compiled_graph(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    graph = agent._build_graph()
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "ainvoke")


async def test_run_processes_pending_file(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    _write_doc(agent.raw_dir)
    await agent.run(max_iterations=1)
    agent.runner.run.assert_called_once()


async def test_run_no_files_does_not_call_runner(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    await agent.run(max_iterations=1)
    agent.runner.run.assert_not_called()


def test_parse_schedule_interval_hours() -> None:
    result = _parse_schedule("interval:hours=12")
    assert result == {"hours": 12}


def test_parse_schedule_on_demand_returns_none() -> None:
    assert _parse_schedule("on-demand") is None


def test_parse_schedule_interval_multi_param() -> None:
    result = _parse_schedule("interval:hours=24,minutes=30")
    assert result == {"hours": 24, "minutes": 30}


def test_start_scheduler_registers_enabled_jobs(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    sources_config = {
        "subagents": {
            "arxiv": {"enabled": True, "schedule": "interval:hours=12"},
            "pubmed": {"enabled": True, "schedule": "interval:hours=48"},
            "google_scholar": {"enabled": False, "schedule": "interval:hours=24"},
        }
    }
    mock_research = MagicMock()
    with patch("llm_rag.supervisor.loop.BackgroundScheduler") as MockSched:
        mock_scheduler = MagicMock()
        MockSched.return_value = mock_scheduler
        agent.start_scheduler(
            topics=["LFP degradation"],
            sources_config=sources_config,
            research_agent=mock_research,
        )
        assert mock_scheduler.add_job.call_count == 2
        mock_scheduler.start.assert_called_once()


def test_stop_scheduler_shuts_down(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    with patch("llm_rag.supervisor.loop.BackgroundScheduler") as MockSched:
        mock_scheduler = MagicMock()
        MockSched.return_value = mock_scheduler
        agent.start_scheduler(
            topics=[],
            sources_config={"subagents": {}},
            research_agent=MagicMock(),
        )
        agent.stop_scheduler()
        mock_scheduler.shutdown.assert_called_once_with(wait=False)
        assert agent._scheduler is None
```

- [ ] **Step 2: Run to verify the four async tests FAIL**

```bash
uv run pytest tests/supervisor/test_loop.py::test_process_one_calls_runner tests/supervisor/test_loop.py::test_process_one_handles_runner_error tests/supervisor/test_loop.py::test_run_processes_pending_file tests/supervisor/test_loop.py::test_run_no_files_does_not_call_runner -v
```

Expected: FAIL — `_process_one_node` and `run()` are still sync

- [ ] **Step 3: Update `src/llm_rag/supervisor/loop.py`**

Replace the `import time` import with nothing (remove it). The `asyncio` import already exists; it stays.

Change `_process_one_node` to async:

```python
async def _process_one_node(self, state: SupervisorState) -> dict[str, Any]:
    pending = list(state["pending_paths"])
    if not pending:
        return {}
    path_str = pending.pop(0)
    try:
        await self.runner.run(Path(path_str))
        return {
            "pending_paths": pending,
            "processed_count": state["processed_count"] + 1,
        }
    except Exception as exc:
        errors = list(state["errors"])
        errors.append(f"{path_str}: {exc}")
        return {
            "pending_paths": pending,
            "error_count": state["error_count"] + 1,
            "errors": errors,
        }
```

Change `run()` to async, replace `time.sleep` with `await asyncio.sleep`, replace `invoke` with `ainvoke`:

```python
async def run(self, max_iterations: int | None = None) -> None:
    self._graph = self._build_graph()
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        initial: SupervisorState = {
            "pending_paths": [],
            "processed_count": 0,
            "error_count": 0,
            "errors": [],
        }
        await self._graph.ainvoke(initial)
        iteration += 1
        more = max_iterations is None or iteration < max_iterations
        if more:
            await asyncio.sleep(self.interval_seconds)
```

Also remove `import time` from the top of `loop.py` (it is no longer used).

- [ ] **Step 4: Run to verify all supervisor tests PASS**

```bash
uv run pytest tests/supervisor/test_loop.py -v
```

Expected: all 14 supervisor tests pass

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Run linting and type checking**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
```

Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/llm_rag/supervisor/loop.py tests/supervisor/test_loop.py
git commit -m "feat: make SupervisorAgent async — ainvoke graph, await runner.run()"
```
