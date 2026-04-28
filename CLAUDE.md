# CLAUDE.md — Battery Research OS

Battery Research OS is a local-first, autonomous research assistant for battery R&D knowledge management. It continuously monitors research sources, ingests documents, extracts structured knowledge into a Pydantic-typed schema, maintains a section-fenced markdown wiki, builds a NetworkX knowledge graph, and answers queries with full provenance citations. All LLM calls go through Claude (Haiku for bulk work, Sonnet for synthesis, Opus for deep analysis and contradiction detection).

---

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available gstack skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/setup-gbrain`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/plan-devex-review`, `/devex-review`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`.

---

## Quick Start

```bash
# Install dependencies (Python 3.11+ required)
uv sync --extra dev

# Configure API keys
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY and FIRECRAWL_API_KEY

# Verify installation
uv run python -c "import llm_rag; print('ok')"
uv run pytest tests/ -v

# Run full autonomous loop
uv run llm-rag run

# Or just ask a question against existing corpus
uv run llm-rag ask "what causes LFP capacity fade?"
```

---

## Repository Layout

```
src/llm_rag/                  Python package — all source code lives here
  __init__.py                 Package root; version
  cli.py                      Typer CLI entry point (llm-rag command) [Plan 6]
  config.py                   pydantic-settings Settings class + get_settings()
  schemas/
    provenance.py             ProvenanceRecord, DocumentManifest, ProcessingStage
    entities.py               EntityType, RelationType, Entity, Material, Cell, Claim,
                              Relation, ExtractionResult
    wiki.py                   WikiSection, WikiPage
  pipeline/                   Five pipeline agents [Plan 2]
    ingestion.py              IngestionAgent — parse + chunk raw docs
    extraction.py             ExtractionAgent — Claude Haiku extracts entities/relations
    normalization.py          NormalizationAgent — canonical name resolution
    wiki_compiler.py          WikiCompilerAgent — section-tagged wiki page merge
    graph_curator.py          GraphCuratorAgent — update NetworkX graph
  research/                   ResearchAgent + SourceSubagents [Plan 3]
    coordinator.py            ResearchAgent — orchestrate searches, dedup by DOI + hash
    subagents/
      arxiv.py                ArXivSubagent — every 12h
      semantic_scholar.py     SemanticScholarSubagent — every 24h
      openalex.py             OpenAlexSubagent — every 24h
      pubmed.py               PubMedSubagent — every 48h
      unpaywall.py            UnpaywallSubagent — on-demand DOI → PDF
      firecrawl.py            FirecrawlSubagent — on-demand URL fetch
      google_scholar.py       GoogleScholarSubagent — stub; needs SERPAPI_KEY
  supervisor/                 SupervisorAgent + file watcher [Plan 4]
    loop.py                   LangGraph StateGraph supervisor loop
    watcher.py                watchdog FileSystemEventHandler for raw/
  query/                      QueryPlanner + AnswerAgent [Plan 5]
    planner.py                LangGraph StateGraph — 4-mode query routing
    retrieval.py              Chroma + wiki scan + NetworkX traversal
    answer.py                 AnswerAgent — synthesize + cite provenance
  wiki/                       Wiki I/O [Plan 2]
    reader.py                 Parse wiki pages; extract named sections
    writer.py                 Section-tagged merge writes (preserve human sections)
  graph/                      NetworkX graph interface [Plan 2]
    store.py                  Load/save/query NetworkX graph
    builder.py                Merge per-doc exports into live graph
  utils/
    hashing.py                content_hash(path) → "sha256:<hex>"
    chunking.py               chunk_text(...) → list[Chunk]; token count ≈ chars/4
    pdf.py                    pdfplumber wrapper; extract_pages(path) → list[PdfPage]
  mcp/                        MCP server layer [SP1 — Agent SDK migration]
    corpus_io.py              FastMCP server — chunk/manifest/export tools
    wiki_io.py                FastMCP server — wiki page read/write tools
    graph_io.py               FastMCP server — entity/relation/normalization tools
    pool.py                   MCPPool — long-lived stdio server process manager
  agent_runner.py             AgentDefinition + run_agent() — shared subagent runner

agents/
  prompts/                    Markdown Claude prompt templates per agent (edit to tune)
  tools/                      Python tool functions available to Claude agents

config/
  settings.yaml               Model assignments, pipeline thresholds (no secrets here)
  sources.yaml                Research topics + per-subagent schedules + max results
  taxonomy.yaml               Battery domain taxonomy: materials, tests, metrics, failures
  entity-normalization.yaml   Canonical entity IDs + known aliases for rule-based resolution
  page-templates/             Wiki page Jinja2-style templates (7 types)
    material.md
    process.md
    test.md
    mechanism.md
    dataset.md
    project.md
    synthesis.md

raw/                          Source documents — the evidence store
  inbox/                      DROP ZONE: PDF, .url, .doi files → auto-detected + ingested
  papers/                     Research papers (PDF or markdown)
  reports/                    Internal reports
  datasets/                   CSV and tabular data
  simulations/                Simulation outputs
  meetings/                   Meeting notes
  sop/                        Standard operating procedures

wiki/                         Markdown knowledge base — the understanding store
  index.md                    Wiki navigation index
  log.md                      Append-only automated change log
  materials/                  One .md file per material entity
  processes/
  tests/
  mechanisms/
  concepts/
  projects/
  datasets/
  reports/
  synthesis/
  heuristics/

graph/
  schema/
    schema.json               Entity + relation type definitions; Neo4j migration guide
  exports/                    Per-document ExtractionResult JSON (intermediate)
  snapshots/                  Periodic full-graph .graphml snapshots (gitignored)

retrieval/
  chunks/                     <doc-id>.jsonl — chunked text with metadata
  embeddings/                 Chroma persistent directory (gitignored — large)
  metadata/                   <doc-id>.json — chunk-level provenance index

docs/
  superpowers/
    specs/
      2026-04-18-battery-research-os-design.md   Full design spec (read this first)
    plans/
      2026-04-19-plan-1-foundation.md            Plan 1 implementation plan
  roadmap.md                  v2 (hardening) and v3 (goal-directed) roadmap

tests/                        pytest test suite
  test_schemas.py             Provenance, entity, relation, wiki schemas (19 tests)
  test_hashing.py             content_hash utility (5 tests)
  test_chunking.py            chunk_text utility (8 tests)
  test_config.py              Settings, model assignments, path properties (7 tests)

pyproject.toml                Build config, dependencies, ruff + mypy + pytest config
uv.lock                       Locked dependency tree (commit this)
.env.example                  API key template (copy to .env, never commit .env)
.gitignore                    Ignores .venv, .env, Chroma embeddings, GraphML snapshots
```

---

## Three Data Stores

The system maintains three separate stores. Understanding which to use for what is important:

### 1. `raw/` + `retrieval/` — Evidence Store

- **`raw/`**: Original source documents. Never delete files here manually; use manifests to control reprocessing.
- **`retrieval/chunks/`**: Chunked JSONL files generated by IngestionAgent. Derived from raw — do not edit.
- **`retrieval/embeddings/`**: Chroma vector store. Derived — do not edit. Delete and re-run `ingest` to rebuild.
- **`retrieval/metadata/`**: Chunk-level provenance index. Derived — do not edit.

### 2. `wiki/` — Understanding Store

- Plain markdown, human-readable, the canonical synthesis layer.
- Sections are either `auto` (machine-managed) or `human` (human-curated).
- **WikiCompilerAgent only rewrites `auto` sections.** Human sections are never touched.
- You may freely edit any `human` section. Your edits survive every `compile-wiki` run.
- Do not edit content between `auto-start` / `auto-end` tags — it will be overwritten.

### 3. `graph/` — Relations Store

- **`graph/exports/`**: Per-document ExtractionResult JSON + normalized JSON. Generated by pipeline.
- **`graph/snapshots/`**: Full-graph GraphML snapshots. Derived — do not edit.
- The live graph is rebuilt from `exports/` using `build-graph`. Do not edit exports directly.

---

## Wiki Section Fencing — Critical Rule

Every wiki page uses HTML comment fences to mark section ownership. This is the single most important convention in the system.

```markdown
## Evidence
<!-- auto-start: evidence -->
| Source | Claim | Confidence | Extracted |
|--------|-------|-----------|-----------|
| papers/sample-lfp-001.md §3.2 | LFP shows 170 mAh/g | 0.92 | 2026-04-18 |
<!-- auto-end: evidence -->

## Summary
<!-- human-start: summary -->
LFP is the dominant cathode for long-cycle-life applications. See evidence below.
<!-- human-end: summary -->

## Open Questions
<!-- human-start: open-questions -->
- What is the rate capability at 5C for our specific cell format?
<!-- human-end: open-questions -->
```

**Rules:**
1. `<!-- auto-start: NAME -->` / `<!-- auto-end: NAME -->` — managed by WikiCompilerAgent. Rewritten on every `compile-wiki` run. Never edit manually.
2. `<!-- human-start: NAME -->` / `<!-- human-end: NAME -->` — managed by humans. Never touched by any agent. Safe to edit freely.
3. Section names must be lowercase and hyphen-separated (e.g., `open-questions`, `linked-entities`).
4. Both tags must be present for the fence to be recognized. A missing closing tag causes the parser to treat all subsequent content as part of that section.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Required** | All Claude API calls (extraction, wiki, queries) |
| `FIRECRAWL_API_KEY` | **Required** | Web scraping for FirecrawlSubagent + .url ingest |
| `SERPAPI_KEY` | Optional | Enables GoogleScholarSubagent (disabled if absent) |

Notes:
- Never commit `.env` — it is in `.gitignore`.
- `Settings` loads from `.env` file AND from actual environment variables (env vars take precedence).
- If a key is absent, the corresponding agent logs a warning and skips; the pipeline continues.
- SerpAPI key being absent only disables GoogleScholarSubagent; all other subagents are unaffected.

---

## Config Files

### `config/settings.yaml`

Controls model assignments and pipeline thresholds. Changes take effect on next run (no restart needed for batch jobs; supervisor loop reads on startup).

```yaml
models:
  bulk_extraction: claude-haiku-4-5-20251001   # ExtractionAgent (cost-sensitive)
  wiki_compilation: claude-sonnet-4-6          # WikiCompilerAgent (synthesis quality)
  contradiction_detection: claude-opus-4-7    # ReviewerAgent (reasoning depth)
  query_synthesis: claude-sonnet-4-6          # AnswerAgent default
  deep_analysis: claude-opus-4-7             # AnswerAgent --quality mode
  relevance_scoring: claude-haiku-4-5-20251001 # paper relevance filter
  supervisor: claude-sonnet-4-6              # SupervisorAgent gap analysis

pipeline:
  chunk_size: 512        # tokens per chunk (approx — actual is chars/4)
  chunk_overlap: 64      # token overlap between adjacent chunks
  relevance_threshold: 0.6  # papers below this score are logged but not downloaded
```

### `config/sources.yaml`

Defines what topics to search and how often each subagent runs. Edit `research_topics` to control what the system monitors. Enable/disable subagents with `enabled: true/false`.

### `config/taxonomy.yaml`

Battery domain taxonomy used for entity classification. Lists known material classes (cathode, anode, electrolyte, separator), failure mechanisms, test types, and key metrics. ExtractionAgent uses this for classification hints.

### `config/entity-normalization.yaml`

Canonical entity definitions with known aliases for rule-based normalization. When the NormalizationAgent encounters a string matching an alias, it maps it to the canonical `entity_id`. Add entries as you encounter new naming inconsistencies in your corpus.

### `config/page-templates/`

Jinja2-style templates for each wiki page type. WikiCompilerAgent instantiates these when creating new pages. The templates define the section structure and fencing. Seven templates:
- `material.md` — chemical formulas, properties, evidence
- `process.md` — protocol steps, materials used
- `test.md` — test conditions, key metrics
- `mechanism.md` — causes, effects, mitigations
- `dataset.md` — schema/columns, provenance
- `project.md` — goals, documents, key entities
- `synthesis.md` — key claims, supporting/contradicting evidence

---

## CLI Commands

All commands are run via `uv run llm-rag <command>` (or `llm-rag <command>` if installed globally).

### Autonomous Operation

```bash
llm-rag run                    # start supervisor loop (polls every 60s by default)
llm-rag run --interval 30      # poll every 30 seconds
llm-rag status                 # show queue length, last run times, corpus stats
```

### Manual Ingest

```bash
llm-rag ingest                          # process all changed files in raw/
llm-rag ingest --path raw/inbox/        # process a specific directory
llm-rag ingest --doc-id papers/2301     # process one specific document by ID
llm-rag ingest --force                  # reprocess regardless of content hash
```

### Research / Fetch

```bash
llm-rag fetch --topic "LFP degradation"  # search all enabled subagents for topic
llm-rag fetch --doi 10.1016/j.xxx        # resolve DOI via Unpaywall, download PDF
llm-rag fetch --url https://...          # fetch URL via Firecrawl
llm-rag fetch --source arxiv             # run only the ArXiv subagent
```

### Knowledge Compilation

```bash
llm-rag compile-wiki                     # update all stale wiki pages
llm-rag compile-wiki --entity material:lfp  # update one specific entity's page
llm-rag build-graph                      # rebuild NetworkX graph from all exports
llm-rag build-graph --rebuild            # force full rebuild (not incremental)
```

### Query

```bash
llm-rag ask "what causes LFP capacity fade?"
llm-rag ask "..." --mode wiki            # wiki-first routing (mechanistic queries)
llm-rag ask "..." --mode vector          # vector-first (evidence retrieval)
llm-rag ask "..." --mode graph           # graph-first (relational queries)
llm-rag ask "..." --mode hybrid          # parallel: Chroma + wiki + graph
llm-rag ask "..." --quality              # use Opus for deep analysis
llm-rag ask "..." --verbose              # show retrieval trace + provenance citations
```

### Maintenance

```bash
llm-rag lint-wiki                        # check wiki pages for broken fences, missing sections
llm-rag lint-wiki --fix                  # auto-fix repairable issues
llm-rag export-graph --format graphml    # export full graph as GraphML
llm-rag export-graph --format cypher     # export as Neo4j-ready Cypher statements
```

---

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_schemas.py -v
uv run pytest tests/test_hashing.py -v
uv run pytest tests/test_chunking.py -v
uv run pytest tests/test_config.py -v

# Filter by test name
uv run pytest -k "material" -v
uv run pytest -k "extraction" -v

# Stop on first failure
uv run pytest tests/ -x -v

# Run with output captured (useful for debugging)
uv run pytest tests/ -v -s

# Lint (ruff)
uv run ruff check src/ tests/
uv run ruff check src/ tests/ --fix    # auto-fix safe issues

# Type checking (mypy strict mode)
uv run mypy src/

# All checks in one go
uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest tests/ -v
```

**Expected test count:** 38 passing tests (19 schema + 5 hashing + 8 chunking + 7 config) after Plan 1. More tests are added in Plans 2–6.

**pytest is configured** in `pyproject.toml` with `asyncio_mode = "auto"`, so `async def test_*` functions work without decorators.

---

## Adding a New Pipeline Agent

Pipeline agents live in `src/llm_rag/pipeline/` and process documents through the stages defined in `ProcessingStage`.

1. **Create the agent file** at `src/llm_rag/pipeline/<name>.py`:
   ```python
   from llm_rag.schemas.provenance import DocumentManifest, ProcessingStage

   class MyNewAgent:
       async def run(self, manifest: DocumentManifest) -> DocumentManifest:
           # ... do work ...
           manifest.stages_completed.append(ProcessingStage.<YOUR_STAGE>)
           return manifest
   ```

2. **Add a `ProcessingStage` value** to `src/llm_rag/schemas/provenance.py` if introducing a new stage.

3. **Create a Claude prompt template** at `agents/prompts/<name>.md`. Use `{{variable}}` syntax for interpolated values. The prompt should specify: input format, output format (JSON schema), extraction instructions, and battery domain context.

4. **Wire into the supervisor** at `src/llm_rag/supervisor/loop.py` — add a node to the LangGraph StateGraph and add the appropriate edge condition.

5. **Write tests** in `tests/pipeline/test_<name>.py`. Test: (a) happy path with sample input, (b) idempotency (running twice produces same result), (c) manifest stage correctly updated.

6. **Update the manifest incremental gate** in the supervisor loop if your agent adds a new downstream stage.

---

## Adding a New Source Subagent

Source subagents live in `src/llm_rag/research/subagents/` and implement the standard `SourceSubagent` interface.

1. **Create the subagent file** at `src/llm_rag/research/subagents/<source>.py`:
   ```python
   from dataclasses import dataclass
   from llm_rag.research.coordinator import CandidateDocument

   class MySourceSubagent:
       async def search(self, topics: list[str]) -> list[CandidateDocument]:
           """Search for papers matching topics. Return candidate documents."""
           ...

       async def fetch(self, candidate: CandidateDocument) -> bytes | None:
           """Download the full document. Return None if unavailable."""
           ...
   ```

2. **Register in the coordinator** at `src/llm_rag/research/coordinator.py` — add to the `subagents` list in `ResearchAgent.__init__`.

3. **Add config** in `config/sources.yaml`:
   ```yaml
   subagents:
     my_source:
       enabled: true
       schedule: "interval:hours=24"
       max_results_per_query: 20
   ```

4. **Add schedule in the supervisor** at `src/llm_rag/supervisor/loop.py` — APScheduler reads the `schedule` field and dispatches the subagent accordingly.

5. **Write tests** in `tests/research/test_<source>.py`. Mock all HTTP calls — never make live API calls in tests.

---

## Document Manifests

Each source document has a sidecar manifest file at `raw/<subdir>/<doc-id>.manifest.json`, placed next to the source file.

**Manifest file structure** (DocumentManifest schema):
```json
{
  "doc_id": "papers/sample-lfp-001",
  "source_path": "raw/papers/sample-lfp-001.md",
  "content_hash": "sha256:abc123...",
  "doc_type": "paper",
  "title": "Capacity Fade in LFP...",
  "authors": ["A. Researcher"],
  "doi": "10.xxxx/...",
  "arxiv_id": null,
  "source_connector": "arxiv",
  "fetched_at": "2026-04-18T10:00:00Z",
  "stages_completed": ["ingested", "extracted", "normalized", "wiki_compiled", "graph_updated"],
  "last_processed": "2026-04-18T10:05:00Z",
  "error": null
}
```

**Incremental reprocessing gate** (evaluated in order):
1. Content hash changed since last manifest → reprocess all stages from scratch
2. A downstream stage is missing from `stages_completed` → run from the first missing stage
3. `--force` flag passed → reprocess all stages from scratch
4. Otherwise → skip (document is up to date)

**To force reprocess a document:**
```bash
# Option 1: delete the manifest (safest)
rm raw/papers/my-paper.manifest.json
uv run llm-rag ingest --doc-id papers/my-paper

# Option 2: use --force flag (processes all documents)
uv run llm-rag ingest --force

# Option 3: force one document by ID
uv run llm-rag ingest --doc-id papers/my-paper --force
```

**Manual drop-zone entries** — files dropped in `raw/inbox/` are routed based on extension:
- `.pdf` → IngestionAgent (pdfplumber)
- `.md` → IngestionAgent (python-frontmatter)
- `.url` → FirecrawlSubagent fetches the URL, then IngestionAgent
- `.doi` → UnpaywallSubagent resolves DOI to PDF, then IngestionAgent

---

## Schema Types

Defined in `src/llm_rag/schemas/entities.py` and `graph/schema/schema.json`.

### 14 Entity Types (`EntityType` enum)

| Enum Value | String | Description |
|---|---|---|
| `DOCUMENT` | `"Document"` | Source paper, report, or document |
| `PROJECT` | `"Project"` | Research project or workstream |
| `MATERIAL` | `"Material"` | Battery material (cathode, anode, electrolyte, separator) |
| `PROCESS` | `"Process"` | Synthesis, assembly, or cycling process |
| `COMPONENT` | `"Component"` | Cell component (current collector, binder, etc.) |
| `FORMULATION` | `"Formulation"` | Specific electrolyte or electrode formulation |
| `CELL` | `"Cell"` | Full cell or half-cell definition |
| `TEST_CONDITION` | `"TestCondition"` | Test protocol conditions (temperature, C-rate, voltage window) |
| `METRIC` | `"Metric"` | Performance metric (capacity, resistance, efficiency) |
| `PROPERTY` | `"Property"` | Material or cell property |
| `FAILURE_MECHANISM` | `"FailureMechanism"` | Degradation or failure mechanism |
| `DATASET` | `"Dataset"` | Experimental or simulation dataset |
| `EXPERIMENT` | `"Experiment"` | Specific experimental run |
| `CLAIM` | `"Claim"` | A factual claim with supporting/contradicting evidence |

**Battery-specific subclasses** (inherit from `Entity`):
- `Material` adds: `formula`, `material_class` (cathode/anode/electrolyte), `crystal_structure`
- `Cell` adds: `chemistry` (e.g., "NMC811/graphite"), `form_factor` (pouch/cylindrical/coin), `capacity_mah`
- `Claim` adds: `statement`, `supported_by` (list of entity_ids), `contradicted_by` (list of entity_ids)

### 15 Relation Types (`RelationType` enum)

| Enum Value | String | Meaning |
|---|---|---|
| `MENTIONS` | `"MENTIONS"` | Document mentions an entity |
| `USES_MATERIAL` | `"USES_MATERIAL"` | Experiment/process uses a material |
| `USES_PROCESS` | `"USES_PROCESS"` | Experiment uses a process |
| `PRODUCES_PROPERTY` | `"PRODUCES_PROPERTY"` | Process produces a property |
| `MEASURED_BY` | `"MEASURED_BY"` | Property measured by a test/metric |
| `TESTED_UNDER` | `"TESTED_UNDER"` | Entity tested under specific conditions |
| `AFFECTS` | `"AFFECTS"` | Entity affects another |
| `ASSOCIATED_WITH` | `"ASSOCIATED_WITH"` | General co-occurrence association |
| `CAUSES` | `"CAUSES"` | Mechanism/process causes a failure or effect |
| `MITIGATES` | `"MITIGATES"` | Intervention mitigates a failure mechanism |
| `CONTRADICTS` | `"CONTRADICTS"` | Claim contradicts another claim |
| `SUPPORTED_BY` | `"SUPPORTED_BY"` | Claim supported by evidence |
| `DERIVED_FROM` | `"DERIVED_FROM"` | Data or entity derived from another |
| `PART_OF` | `"PART_OF"` | Component is part of a larger entity |
| `SIMULATED_BY` | `"SIMULATED_BY"` | Entity simulated by a model or dataset |

**Entity ID convention**: stable slugs in the form `<type>:<name>`. Examples:
- `material:lfp`
- `material:nmc811`
- `mechanism:sei`
- `process:coin-cell-assembly`
- `experiment:batch-a-001`
- `claim:lfp-capacity-001`

---

## Model Assignments

Defined in `config/settings.yaml` and loaded into `Settings` in `src/llm_rag/config.py`.

| Setting key | Model | Used for |
|---|---|---|
| `model_bulk_extraction` | `claude-haiku-4-5-20251001` | ExtractionAgent — per-chunk entity/relation extraction |
| `model_relevance_scoring` | `claude-haiku-4-5-20251001` | ResearchAgent — paper relevance 0.0–1.0 scoring |
| `model_wiki_compilation` | `claude-sonnet-4-6` | WikiCompilerAgent — synthesize auto sections |
| `model_query_synthesis` | `claude-sonnet-4-6` | AnswerAgent default mode |
| `model_supervisor` | `claude-sonnet-4-6` | SupervisorAgent gap analysis |
| `model_contradiction` | `claude-opus-4-7` | ReviewerAgent contradiction detection |
| `model_deep_analysis` | `claude-opus-4-7` | AnswerAgent `--quality` mode |

**Override via environment variable**: Any `Settings` field can be overridden in `.env`. For example, to use Sonnet for extraction during testing: `MODEL_BULK_EXTRACTION=claude-sonnet-4-6`.

---

## Agent Overview Table

| # | Agent | Module | Claude Model | Input | Output |
|---|---|---|---|---|---|
| 1 | SupervisorAgent | `supervisor/loop.py` | Sonnet | System state | Dispatch queue |
| 2 | ResearchAgent | `research/coordinator.py` | Haiku (scoring) | Topics + schedules | raw/inbox/ files |
| 3 | IngestionAgent | `pipeline/ingestion.py` | None | Raw file | chunks JSONL + metadata |
| 4 | ExtractionAgent | `pipeline/extraction.py` | Haiku / Sonnet | Chunks | ExtractionResult JSON |
| 5 | NormalizationAgent | `pipeline/normalization.py` | Haiku + Sonnet | Raw entities | Normalized entities |
| 6 | WikiCompilerAgent | `pipeline/wiki_compiler.py` | Sonnet | ExtractionResult | Updated wiki .md files |
| 7 | GraphCuratorAgent | `pipeline/graph_curator.py` | None | ExtractionResult | Updated NetworkX graph |
| 8 | QueryPlannerAgent + AnswerAgent | `query/planner.py` + `query/answer.py` | Sonnet / Opus | Query string | Markdown answer + citations |
| 9 | ReviewerAgent | (Plan 4) | Sonnet | Wiki pages | Lint report + contradiction flags |

**Note on IngestionAgent and GraphCuratorAgent**: These agents make no LLM calls. IngestionAgent uses pdfplumber/python-frontmatter + the chunking utility. GraphCuratorAgent is pure NetworkX operations.

---

## QueryPlanner Routing Logic

The QueryPlanner (LangGraph StateGraph in `query/planner.py`) classifies query intent and routes to the appropriate retrieval strategy:

| Intent class | Route | Retrieval method |
|---|---|---|
| `"mechanistic"` | wiki-first | Scan wiki pages for mechanistic descriptions |
| `"evidence"` | vector-first | Chroma similarity search over raw chunks |
| `"relational"` | graph-first | NetworkX traversal from query entities |
| `"synthesis"` | hybrid | Parallel: Chroma + wiki scan + NetworkX |

After retrieval, `check_sufficient` evaluates result quality and may expand to secondary sources. `synthesize` calls Claude with inline provenance placeholders. `format_response` produces markdown + source list + confidence.

---

## Plan Sequence

The codebase is built in 6 plans, each building on the previous. If a module is a stub, it belongs to a later plan.

| Plan | Status | What it builds |
|---|---|---|
| **Plan 1: Foundation** | Complete | Pydantic schemas, utils (hashing, chunking, pdf stub), config module, YAML configs, wiki templates, sample data, tests |
| **Plan 2: Ingest Pipeline** | Complete | IngestionAgent, ExtractionAgent, NormalizationAgent, WikiCompilerAgent, GraphCuratorAgent, wiki reader/writer, graph store/builder |
| **Plan 3: Research Agent** | Complete | ResearchAgent coordinator, 6 SourceSubagents (arXiv, SemanticScholar, OpenAlex, PubMed, Unpaywall, Firecrawl) |
| **Plan 4: Supervisor + Runtime** | Complete | SupervisorAgent LangGraph loop, watchdog file watcher, APScheduler source scheduling, ReviewerAgent |
| **Plan 5: Query Layer** | Stub stubs exist | QueryPlannerAgent LangGraph, Chroma retrieval, wiki scan, NetworkX traversal, AnswerAgent |
| **Plan 6: CLI Integration** | Stub stubs exist | Typer CLI (`cli.py`), all `llm-rag` commands wired end-to-end |

All module stubs (empty `__init__.py` files) are in place so imports do not fail. Plans 2–6 fill in the implementations.

---

## Design Documentation

| Document | Location | Purpose |
|---|---|---|
| Full design spec | `docs/superpowers/specs/2026-04-18-battery-research-os-design.md` | Complete architecture, schemas, agent designs, data flow, library choices, assumptions |
| Plan 1 implementation | `docs/superpowers/plans/2026-04-19-plan-1-foundation.md` | Task-by-task TDD plan for foundation layer |
| v2 / v3 Roadmap | `docs/roadmap.md` | v2: hardening + full integrations; v3: goal-directed autonomous research |

## MCP Gateway

The Cloudflare-protected MCP-over-HTTP gateway is documented in
`docs/api/v1.md`. Reference writing-app integrations live in
`examples/writing-app/` and cover Claude Desktop, Cursor, and a small Python
client.

**If you are starting a new Claude Code session:** Read the design spec first (30 min), then this CLAUDE.md, then look at `src/llm_rag/schemas/` to understand the data models. The schemas are the source of truth for all data structures in the system.

---

## Common Gotchas

1. **`get_settings()` is cached**: `lru_cache(maxsize=1)` means Settings is a singleton per process. In tests that need different settings, use `get_settings.cache_clear()` before constructing a new instance.

2. **Chunking uses character approximation**: `token_count = len(text) // 4`. This is intentional — the system does not tokenize with a real tokenizer for chunking to avoid the overhead. For Claude context window management, the real token count may differ by ±20%.

3. **Wiki section names must match exactly**: The wiki reader/writer uses the section name as the dictionary key. `"open-questions"` and `"open_questions"` are different keys. Always use hyphenated lowercase.

4. **Manifests live next to source files**: `raw/papers/my-paper.manifest.json` not `raw/manifests/my-paper.manifest.json`. The manifest path is derived from the source path by replacing the extension with `.manifest.json`.

5. **Graph exports are per-document, not merged**: `graph/exports/<doc-id>.json` is the raw ExtractionResult for one document. The merged live graph is the NetworkX object in memory, persisted to `graph/snapshots/latest.graphml`. GraphCuratorAgent merges on each ingest run.

6. **Chroma embeddings are in `.gitignore`**: `retrieval/embeddings/` is excluded. On a fresh clone, run `llm-rag ingest` to rebuild the vector index from the chunked JSONL files.

7. **Overriding project root in tests**: Tests that write to a tmp directory must set `ROOT_DIR` before clearing the cache: `monkeypatch.setenv("ROOT_DIR", str(tmp_path))` then `get_settings.cache_clear()`. Always call `get_settings.cache_clear()` again in teardown (end of test).

8. **`claude-code-sdk` package**: PyPI package is `claude-code-sdk` (not `anthropic-agent-sdk`). `query()` is an **async generator** — iterate with `async for message in query(...)`, never `await query(...)`. `McpStdioServerConfig` is a TypedDict, not a dataclass.

---

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
