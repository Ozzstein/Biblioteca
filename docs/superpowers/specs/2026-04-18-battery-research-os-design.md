# Battery Research OS — Design Spec

**Date:** 2026-04-18  
**Status:** Approved  
**Project:** `llm_rag`

---

## 1. Purpose

A production-quality, local-first, autonomous research assistant for battery R&D knowledge management. The system continuously monitors sources, ingests documents, extracts structured knowledge, maintains a markdown wiki, builds a knowledge graph, and answers queries — all with full provenance.

**Three stores, one pipeline, one query layer:**

| Store | Role | Format |
|---|---|---|
| `wiki/` | System of understanding | Plain markdown, human-editable |
| `graph/` | System of relations | NetworkX + JSON/GraphML |
| `raw/` + `retrieval/` | System of evidence | Raw files + Chroma vector store |

---

## 2. Architecture Overview

```
[Source Connectors]  →  raw/inbox/
[File Watcher]       →  detects new/changed files
[SupervisorAgent]    →  orchestrates all work (LangGraph loop)
  → dispatches to:
      [ResearchAgent + SourceSubagents]  →  search, fetch, dedup
      [Ingest Pipeline]                  →  process documents
          IngestionAgent   → parse + chunk
          ExtractionAgent  → entities, claims, relations (Claude)
          NormalizationAgent → canonical names
          WikiCompilerAgent  → section-tagged wiki merge (Claude)
          GraphCuratorAgent  → NetworkX graph update
      [ReviewerAgent]      →  lint wiki, flag contradictions

[QueryPlannerAgent + AnswerAgent]  →  on-demand via `ask` (LangGraph)
```

### Runtime Components

Three concurrent processes when `llm-rag run` is active:

1. **SupervisorAgent loop** — LangGraph StateGraph, polls continuously
2. **Source scheduler** — APScheduler, triggers SourceSubagents on configured intervals
3. **File watcher** — watchdog, detects changes in `raw/` and `raw/inbox/`

---

## 3. Repository Structure

```
llm_rag/
├── raw/
│   ├── inbox/                    # drop zone: PDF, .url, .doi files
│   ├── papers/
│   ├── reports/
│   ├── datasets/
│   ├── simulations/
│   ├── meetings/
│   └── sop/
├── wiki/
│   ├── index.md
│   ├── log.md
│   ├── projects/
│   ├── concepts/
│   ├── materials/
│   ├── processes/
│   ├── tests/
│   ├── mechanisms/
│   ├── datasets/
│   ├── reports/
│   ├── synthesis/
│   └── heuristics/
├── graph/
│   ├── schema/
│   │   └── schema.json           # entity + relation type definitions
│   ├── exports/
│   │   └── <doc-id>.json         # per-document extracted graph objects
│   └── snapshots/
│       └── <date>.graphml        # periodic full-graph NetworkX snapshots
├── retrieval/
│   ├── chunks/
│   │   └── <doc-id>.jsonl        # chunked text with metadata
│   ├── embeddings/               # Chroma persistent directory
│   └── metadata/
│       └── <doc-id>.json         # chunk-level provenance index
├── agents/
│   ├── prompts/                  # markdown prompt templates per agent
│   └── tools/                    # Python tool functions available to agents
├── src/
│   └── llm_rag/
│       ├── __init__.py
│       ├── cli.py                # Typer CLI entry point
│       ├── config.py             # settings, paths, model selection
│       ├── schemas/
│       │   ├── entities.py       # Pydantic entity/relation models
│       │   ├── provenance.py     # ProvenanceRecord, DocumentManifest
│       │   └── wiki.py           # WikiPage, WikiSection models
│       ├── pipeline/
│       │   ├── ingestion.py      # IngestionAgent
│       │   ├── extraction.py     # ExtractionAgent
│       │   ├── normalization.py  # NormalizationAgent
│       │   ├── wiki_compiler.py  # WikiCompilerAgent
│       │   └── graph_curator.py  # GraphCuratorAgent
│       ├── research/
│       │   ├── coordinator.py    # ResearchAgent coordinator
│       │   └── subagents/
│       │       ├── arxiv.py
│       │       ├── semantic_scholar.py
│       │       ├── openalex.py
│       │       ├── pubmed.py
│       │       ├── unpaywall.py
│       │       ├── firecrawl.py
│       │       └── google_scholar.py   # stub, SerpAPI-gated
│       ├── supervisor/
│       │   ├── loop.py           # LangGraph supervisor StateGraph
│       │   └── watcher.py        # watchdog file watcher
│       ├── query/
│       │   ├── planner.py        # LangGraph query StateGraph
│       │   ├── retrieval.py      # vector + wiki + graph retrieval
│       │   └── answer.py         # AnswerAgent
│       ├── graph/
│       │   ├── store.py          # NetworkX load/save/query interface
│       │   └── builder.py        # merge per-doc exports into live graph
│       ├── wiki/
│       │   ├── reader.py         # parse wiki pages, extract sections
│       │   └── writer.py         # section-tagged merge writes
│       └── utils/
│           ├── chunking.py
│           ├── hashing.py
│           └── pdf.py            # pdfplumber wrapper
├── config/
│   ├── settings.yaml             # model assignments, thresholds
│   ├── sources.yaml              # research topics, subagent schedules
│   ├── taxonomy.yaml
│   ├── entity-normalization.yaml
│   └── page-templates/           # .md templates per wiki page type
├── tests/
├── scripts/
├── docs/
│   ├── roadmap.md
│   └── superpowers/
│       └── specs/
├── pyproject.toml
├── README.md
└── CLAUDE.md
```

---

## 4. Core Schemas

### ProvenanceRecord

```python
class ExtractionMethod(str, Enum):
    CLAUDE_HAIKU = "claude-haiku"
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    RULE_BASED = "rule-based"
    MANUAL = "manual"

class ProvenanceRecord(BaseModel):
    source_doc_id: str
    source_path: str
    section: str | None          # "§3.2", "Table 4", "p.12"
    timestamp: datetime
    confidence: float            # 0.0 – 1.0
    extraction_method: ExtractionMethod
    extractor_model: str | None  # e.g. "claude-haiku-4-5-20251001"
```

### DocumentManifest

```python
class ProcessingStage(str, Enum):
    INGESTED = "ingested"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    WIKI_COMPILED = "wiki_compiled"
    GRAPH_UPDATED = "graph_updated"

class DocumentManifest(BaseModel):
    doc_id: str
    source_path: str
    content_hash: str            # SHA-256, drives incremental reprocessing
    doc_type: str                # "paper", "report", "sop", "meeting"
    title: str | None
    authors: list[str]
    doi: str | None
    arxiv_id: str | None
    source_connector: str        # "arxiv", "manual", "firecrawl", etc.
    fetched_at: datetime
    stages_completed: list[ProcessingStage]
    last_processed: datetime
    error: str | None
```

### Entity Types

```python
class EntityType(str, Enum):
    DOCUMENT = "Document"
    PROJECT = "Project"
    MATERIAL = "Material"
    PROCESS = "Process"
    COMPONENT = "Component"
    FORMULATION = "Formulation"
    CELL = "Cell"
    TEST_CONDITION = "TestCondition"
    METRIC = "Metric"
    PROPERTY = "Property"
    FAILURE_MECHANISM = "FailureMechanism"
    DATASET = "Dataset"
    EXPERIMENT = "Experiment"
    CLAIM = "Claim"

class Entity(BaseModel):
    entity_id: str               # stable slug e.g. "material:lfp"
    entity_type: EntityType
    canonical_name: str
    aliases: list[str]
    provenance: list[ProvenanceRecord]
    properties: dict[str, Any]
    wiki_page: str | None

# Battery-specific subclasses (selected):

class Material(Entity):
    formula: str | None
    material_class: str | None   # "cathode", "electrolyte", "anode"
    crystal_structure: str | None

class Cell(Entity):
    chemistry: str | None        # "NMC811/graphite"
    form_factor: str | None      # "pouch", "cylindrical", "coin"
    capacity_mah: float | None

class Claim(Entity):
    statement: str
    supported_by: list[str]      # entity_ids
    contradicted_by: list[str]   # entity_ids
```

### Relation Types

```python
class RelationType(str, Enum):
    MENTIONS = "MENTIONS"
    USES_MATERIAL = "USES_MATERIAL"
    USES_PROCESS = "USES_PROCESS"
    PRODUCES_PROPERTY = "PRODUCES_PROPERTY"
    MEASURED_BY = "MEASURED_BY"
    TESTED_UNDER = "TESTED_UNDER"
    AFFECTS = "AFFECTS"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    CAUSES = "CAUSES"
    MITIGATES = "MITIGATES"
    CONTRADICTS = "CONTRADICTS"
    SUPPORTED_BY = "SUPPORTED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    PART_OF = "PART_OF"
    SIMULATED_BY = "SIMULATED_BY"

class Relation(BaseModel):
    relation_id: str
    relation_type: RelationType
    source_entity_id: str
    target_entity_id: str
    provenance: list[ProvenanceRecord]
    weight: float = 1.0

class ExtractionResult(BaseModel):
    doc_id: str
    entities: list[Entity]
    relations: list[Relation]
    chunks_processed: int
    extraction_model: str
    extracted_at: datetime
```

### Wiki Page Model

```python
class WikiSection(BaseModel):
    name: str
    managed_by: Literal["auto", "human"]
    content: str

class WikiPage(BaseModel):
    page_type: str               # "material", "process", "test", etc.
    entity_id: str
    canonical_name: str
    path: str
    sections: dict[str, WikiSection]
    last_auto_updated: datetime | None
    last_human_edited: datetime | None
```

**Section tagging convention in markdown:**

```markdown
## Evidence
<!-- auto-start: evidence -->
| Source | Claim | Confidence | Extracted |
|--------|-------|-----------|-----------|
| paper-001.pdf §3.2 | LFP shows 170 mAh/g | 0.92 | 2026-04-18 |
<!-- auto-end: evidence -->

## Open Questions
<!-- human-start: open-questions -->
- What is the rate capability at 5C?
<!-- human-end: open-questions -->
```

The `WikiCompilerAgent` only rewrites `auto` sections. Human sections are never touched.

---

## 5. Agent Design

### Model Assignments

```yaml
# config/settings.yaml
models:
  bulk_extraction: claude-haiku-4-5-20251001
  wiki_compilation: claude-sonnet-4-6
  contradiction_detection: claude-opus-4-7
  query_synthesis: claude-sonnet-4-6
  deep_analysis: claude-opus-4-7
  relevance_scoring: claude-haiku-4-5-20251001
  supervisor_gap_analysis: claude-sonnet-4-6
```

### Agent Summary

| # | Agent | Claude Model | Input → Output |
|---|---|---|---|
| 1 | SupervisorAgent | Sonnet | System state → dispatch queue |
| 2 | ResearchAgent + SourceSubagents | Haiku (scoring) | Topics + sources → raw/inbox/ |
| 3 | IngestionAgent | None | Raw file → chunks JSONL |
| 4 | ExtractionAgent | Haiku / Sonnet | Chunks → ExtractionResult |
| 5 | NormalizationAgent | Haiku + Sonnet | Raw entities → canonical entities |
| 6 | WikiCompilerAgent | Sonnet | ExtractionResult + wiki page → updated page |
| 7 | GraphCuratorAgent | None | ExtractionResult → NetworkX graph |
| 8 | QueryPlannerAgent + AnswerAgent | Sonnet / Opus | Query → routed retrieval → answer |
| 9 | ReviewerAgent | Sonnet | Wiki pages → lint report |

### Incremental Reprocessing Gate

```
content_hash changed?   → run all stages from scratch
stage missing in manifest → run that stage and all downstream
--force flag?           → run all stages from scratch
otherwise               → skip
```

### ResearchAgent — SourceSubagents

Each subagent runs independently via asyncio. The coordinator deduplicates by DOI + content hash before download.

| Subagent | Source | Schedule | V1 Status |
|---|---|---|---|
| ArXivSubagent | arXiv API | every 12h | Full |
| SemanticScholarSubagent | S2 API + citation monitoring | every 24h | Full |
| OpenAlexSubagent | OpenAlex API | every 24h | Full |
| PubMedSubagent | E-utilities API | every 48h | Full |
| UnpaywallSubagent | DOI → open access PDF | on-demand | Full |
| FirecrawlSubagent | Any URL, ResearchGate | on-demand | Full |
| GoogleScholarSubagent | SerpAPI / Firecrawl | every 24h | Stub (SerpAPI key optional) |
| ElsevierSubagent | ScienceDirect API | every 48h | Stub (v2) |

**Relevance scoring:** Claude Haiku receives abstract + research topics → returns 0.0–1.0 score. Papers below `relevance_threshold` (default 0.6) are logged but not downloaded.

**Manual entry points:**
```
raw/inbox/paper.pdf   → auto-detected, routed to pipeline
raw/inbox/paper.url   → fetched via Firecrawl, then pipeline
raw/inbox/paper.doi   → resolved via Unpaywall, then pipeline
```

### QueryPlanner — Routing Logic

LangGraph StateGraph with 4 routing modes:

```
[receive_query]
  → [classify_intent]
      "mechanistic"  → wiki-first
      "evidence"     → vector-first
      "relational"   → graph-first
      "synthesis"    → hybrid
  → [retrieve]       (parallel: Chroma + wiki scan + NetworkX traversal)
  → [check_sufficient] → expand to secondary sources if weak
  → [synthesize]     (Claude with inline provenance citations)
  → [format_response] (markdown answer + source list + confidence)
```

---

## 6. Data Flow

Manifest files live at `raw/<subdir>/<doc-id>.manifest.json`, next to their source file.

```
raw/inbox/ (PDF / .url / .doi)
    ↓ file watcher
DocumentManifest created → raw/<subdir>/<doc-id>.manifest.json
    ↓ IngestionAgent
retrieval/chunks/<doc-id>.jsonl
retrieval/metadata/<doc-id>.json
Chroma embeddings updated
    ↓ ExtractionAgent (Claude Haiku)
graph/exports/<doc-id>.json  (ExtractionResult)
    ↓ NormalizationAgent
graph/exports/<doc-id>.normalized.json
    ↓ WikiCompilerAgent (Claude Sonnet)
wiki/<type>/<entity>.md  (auto sections updated)
wiki/log.md appended
    ↓ GraphCuratorAgent
graph/snapshots/latest.graphml (NetworkX updated)
manifest stages_completed updated
```

---

## 7. Wiki Page Templates

Seven templates in `config/page-templates/`:
`material.md`, `process.md`, `test.md`, `mechanism.md`, `dataset.md`, `project.md`, `synthesis.md`

Each template includes these sections with correct auto/human tagging:
- **Summary** (human)
- **Linked Entities** (auto)
- **Evidence** (auto)
- **Contradictions** (auto)
- **Open Questions** (human)
- **Last Updated** (auto)

---

## 8. CLI Commands

```bash
# Autonomous operation
llm-rag run                              # start supervisor loop
llm-rag run --interval 30               # poll every 30s
llm-rag status                           # queue, last runs, corpus stats

# Manual ingest
llm-rag ingest
llm-rag ingest --path raw/inbox/
llm-rag ingest --doc-id papers/2301
llm-rag ingest --force

# Research / fetch
llm-rag fetch --topic "LFP degradation"
llm-rag fetch --doi 10.1016/...
llm-rag fetch --url https://...
llm-rag fetch --source arxiv

# Knowledge compilation
llm-rag compile-wiki
llm-rag compile-wiki --entity material:lfp
llm-rag build-graph
llm-rag build-graph --rebuild

# Query
llm-rag ask "what causes LFP capacity fade?"
llm-rag ask "..." --mode wiki|vector|graph|hybrid
llm-rag ask "..." --quality              # use Opus
llm-rag ask "..." --verbose              # show retrieval trace + provenance

# Maintenance
llm-rag lint-wiki
llm-rag lint-wiki --fix
llm-rag export-graph --format graphml
llm-rag export-graph --format cypher     # Neo4j-ready
```

---

## 9. Libraries

| Category | Library | Reason |
|---|---|---|
| Orchestration | `langgraph` | Supervisor loop + query planner |
| LLM | `anthropic` | Direct SDK, prompt caching, structured output |
| CLI | `typer` | Typed, minimal boilerplate |
| Vector store | `chromadb` | Embedded, no server, persistent |
| Embeddings | `sentence-transformers` | Local, no API cost |
| Graph | `networkx` | In-memory, GraphML I/O, Neo4j-ready schema |
| PDF | `pdfplumber` | Table-aware, layout-aware |
| Markdown | `python-frontmatter` | YAML frontmatter + body |
| File watching | `watchdog` | Cross-platform filesystem events |
| Scheduling | `apscheduler` | Per-subagent schedules |
| HTTP | `httpx` | Async-native |
| arXiv | `arxiv` | Official Python client |
| Web scraping | `firecrawl-py` | URL fetch + scraping |
| Scholar | `serpapi` | Google Scholar (key-gated, optional) |
| Data | `pandas` | CSV/tabular ingestion |
| Validation | `pydantic` + `pydantic-settings` | All schemas + config |
| Package mgmt | `uv` | Fast, lockfile-based |
| Testing | `pytest` + `pytest-asyncio` | Async pipeline testing |
| Linting | `ruff` + `mypy` | Type checking throughout |

---

## 10. V1 Scope

**Fully implemented:**
- All 9 agents
- 6 source subagents (arXiv, SemanticScholar, OpenAlex, PubMed, Unpaywall, Firecrawl)
- Manifest-driven incremental pipeline
- File watcher + `raw/inbox/` auto-routing
- PDF, markdown, URL, CSV ingestion
- Claude-based extraction with full provenance
- Entity normalization (rule-based + Claude fallback)
- Section-tagged wiki merge (auto/human fencing)
- NetworkX graph with JSON/GraphML persistence
- Chroma vector store with local embeddings
- Full 4-mode query planner (LangGraph)
- All CLI commands
- Battery domain schema (14 entity types, 15 relation types)
- 7 wiki page templates
- Sample data in `raw/` covering all doc types
- `pyproject.toml`, `README.md`, `CLAUDE.md`
- Tests: core schemas, extraction pipeline path, query planner routing

**Stubbed / deferred to v2:**
- GoogleScholarSubagent (interface defined, SerpAPI call stubbed)
- ElsevierSubagent (interface defined, no live calls)
- Neo4j live connection (export format ready, connector stubbed)
- Supervisor gap-driven query generation (heuristic only; Claude-driven in v2)

---

## 11. Explicit Assumptions

1. Claude API key available in environment (`ANTHROPIC_API_KEY`)
2. Firecrawl API key available for web scraping (`FIRECRAWL_API_KEY`)
3. SerpAPI key optional — GoogleScholarSubagent is disabled if absent
4. All data stays local; no cloud storage in v1
5. NetworkX graph fits in memory (up to ~100k nodes is fine for a research corpus)
6. Chroma runs embedded (no server process needed)
7. `sentence-transformers` model downloaded on first run (~90MB)
8. pdfplumber handles standard academic PDFs; scanned/image PDFs are out of scope for v1
9. Wiki pages are the canonical human-readable record. Graph and vector store are derived from raw documents only — the wiki is the human synthesis layer on top, not an input to extraction.
10. Neo4j migration path: NetworkX node/edge schema matches Cypher model exactly
