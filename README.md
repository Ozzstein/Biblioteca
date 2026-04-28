# Battery Research OS — llm-rag

**Production-ready V2 RAG pipeline** for battery R&D knowledge management. Extracts structured knowledge from documents using Claude, maintains a human-readable markdown wiki, builds a NetworkX knowledge graph, and answers queries with full provenance citations — all running locally with **544 passing tests**.

```
Status: ✅ Production-Ready (Phases 0-5 Complete)
Tests: 544 passed, 1 skipped
Architecture: V2 (Evidence → Claims → Graph/Wiki Projections)
Supervisor: Autonomous loop with APScheduler + watchdog
```

---

## Key Features

### Core Pipeline (Phases 0-3)
- **Multi-format ingestion**: PDFs (pdfplumber), markdown, URLs, DOIs, CSVs, meeting notes — drop files in `raw/inbox/` for instant processing
- **Structured extraction**: Claude Haiku extracts 14 entity types and 15 relation types from each document with per-chunk provenance records
- **Typed contracts**: 9 Pydantic models enforce schema validation at every pipeline stage (fail-fast behavior)
- **Phased query retrieval**: QueryAgent gathers context in three phases (evidence → wiki → graph), then synthesizes an answer with inline provenance citations
- **Retry logic**: Exponential backoff (2s–60s, 3 attempts) with dead-letter handling for permanent failures

### V2 Architecture (Phase 4)
- **Canonical evidence schemas**: `EvidenceDocument`, `EvidenceChunk`, `ProvenanceSpan` — source of truth for all knowledge
- **Claim/fact schemas**: `Claim`, `Fact`, `EntityClaim`, `RelationClaim` — first-class assertions (not buried in graph/wiki)
- **Deterministic materializers**: `GraphMaterializer` and `WikiMaterializer` rebuild outputs from claims on demand
- **Human-safe wiki**: `auto-start`/`auto-end` sections (machine-managed) + `human-start`/`human-end` sections (never overwritten)
- **Full provenance**: Every claim, entity, and wiki section traces back to source document, section, and page number

### Battery-Domain Schema
- **14 entity types**: Material, Component, Cell, Formulation, Process, Dataset, Property, Mechanism, Claim, Document, Project, Synthesis, Test, Property
- **15 relation types**: USES_MATERIAL, HAS_COMPONENT, CAUSES, MITIGATES, MEASURES, IMPROVES, DEGRADES, etc.
- **Alias resolution**: `config/entity-normalization.yaml` maps synonyms to canonical IDs (e.g., "LFP" → "lithium-iron-phosphate")

---

## Quick Start

```bash
# 1. Install (Python 3.11+ and uv required)
uv sync --extra dev

# 2. Configure API keys
cp .env.example .env
#    → edit .env: add ANTHROPIC_API_KEY and FIRECRAWL_API_KEY

# 3. Check system status
uv run llm-rag status

# 4. Drop a document in the inbox
cp my_paper.pdf raw/inbox/

# 5. Process it through the full pipeline
uv run llm-rag ingest

# 6. Ask a question
uv run llm-rag ask "what causes LFP capacity fade?"
```

**Ask options:**
- `--quality` — use Opus for deep analysis
- `--verbose` — show retrieval trace and citations
- `--mode hybrid` — combine evidence + wiki + graph retrieval

---

## Architecture

### V2 Data Flow (Current)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DOCUMENT INGESTION                                │
│  raw/inbox/ → PipelineRunner → EvidenceDocument + EvidenceChunk + Provenance│
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CANONICAL EVIDENCE STORE                            │
│  EvidenceStore (source of truth: documents, chunks, byte offsets, pages)    │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CLAIM EXTRACTION (Claude)                            │
│  EntityClaim, RelationClaim, Fact (confidence ≥0.9, multi-evidence)         │
│  ClaimCollection (document-scoped container with evidence references)       │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     │                               │
                     ▼                               ▼
        ┌─────────────────────┐         ┌─────────────────────┐
        │  GraphMaterializer  │         │  WikiMaterializer   │
        │  (projection)       │         │  (projection)       │
        │                     │         │                     │
        │  Claims → Nodes     │         │  Claims + Evidence  │
        │  Relations → Edges  │         │  → Wiki Pages       │
        │  Deterministic      │         │  Preserves human    │
        └──────────┬──────────┘         └──────────┬──────────┘
                   │                               │
                   ▼                               ▼
        ┌─────────────────────┐         ┌─────────────────────┐
        │   graph/exports/    │         │      wiki/          │
        │   latest.graphml    │         │   (entity pages)    │
        │   (NetworkX)        │         │   auto + human      │
        └──────────┬──────────┘         └──────────┬──────────┘
                   │                               │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
        ┌─────────────────────────────────────────────────────────┐
        │                    QueryAgent                            │
        │  Phased retrieval: evidence → wiki → graph → synthesis   │
        │  Citations: [EVIDENCE:doc:chunk] [WIKI:path] [GRAPH:id]  │
        └─────────────────────────────────────────────────────────┘
```

### Agent Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT ECOSYSTEM                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐         ┌─────────────────────────────────────────┐
│   ResearchAgent      │         │          PipelineRunner                 │
│   (fetches papers)   │         │      (processes documents)              │
│                      │         │                                         │
│  ┌────────────────┐  │         │  ┌───────────────────────────────────┐  │
│  │ ArXivSubagent  │──┼─────────┼─▶│ Stage 1: Ingestion                │  │
│  └────────────────┘  │         │  │   - PDF parsing (pdfplumber)      │  │
│  ┌────────────────┐  │         │  │   - Chunking (512 tokens)         │  │
│  │SemanticScholar │──┼─────────┼─▶│   - Embedding (sentence-transformers)│
│  └────────────────┘  │         │  └──────────────┬────────────────────┘  │
│  ┌────────────────┐  │         │                 │                       │
│  │ OpenAlex       │──┤         │                 ▼                       │
│  └────────────────┘  │         │  ┌───────────────────────────────────┐  │
│  ┌────────────────┐  │         │  │ Stage 2: Extraction (Claude)      │  │
│  │ PubMed         │──┤         │  │   - 14 entity types               │  │
│  └────────────────┘  │         │  │   - 15 relation types             │  │
│  ┌────────────────┐  │         │  │   - Per-chunk provenance          │  │
│  │ Firecrawl      │──┤         │  └──────────────┬────────────────────┘  │
│  └────────────────┘  │         │                 │                       │
│                      │         │                 ▼                       │
│  Output:             │         │  ┌───────────────────────────────────┐  │
│  raw/inbox/*.md      │         │  │ Stage 3: Normalization            │  │
│  raw/inbox/*.pdf     │         │  │   - Alias resolution              │  │
└──────────────────────┘         │  │   - Canonical ID generation       │  │
                                 │  └──────────────┬────────────────────┘  │
                                 │                 │                       │
                                 │                 ▼                       │
                                 │  ┌───────────────────────────────────┐  │
                                 │  │ Stage 4: Claim Collection         │  │
                                 │  │   - EntityClaim                   │  │
                                 │  │   - RelationClaim                 │  │
                                 │  │   - Fact (confidence ≥0.9)        │  │
                                 │  └──────────────┬────────────────────┘  │
                                 └─────────────────┼───────────────────────┘
                                                   │
                                                   ▼
                                 ┌─────────────────────────────────────────┐
                                 │         ClaimCollection (JSON)          │
                                 │         graph/exports/*.json            │
                                 └─────────────────┬───────────────────────┘
                                                   │
                     ┌─────────────────────────────┼─────────────────────────┐
                     │                             │                         │
                     ▼                             ▼                         ▼
        ┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
        │  GraphMaterializer  │      │  WikiMaterializer   │      │    QueryAgent       │
        │                     │      │                     │      │                     │
        │  Input: Claims      │      │  Input: Claims      │      │  Input: User query  │
        │  Output: GraphML    │      │  Output: Markdown   │      │                     │
        │                     │      │                     │      │  Phase 1: Claims    │
        │  - Claims → Nodes   │      │  - Claims → Pages   │      │  Phase 2: Wiki      │
        │  - Relations → Edges│      │  - Evidence → Tables│      │  Phase 3: Graph     │
        │  - Stubs for orphan │      │  - Preserve human   │      │  Phase 4: Evidence  │
        │    entities         │      │    sections         │      │                     │
        └──────────┬──────────┘      └──────────┬──────────┘      │  Output: Answer +   │
                     │                          │                 │  Citations          │
                     ▼                          ▼                 └──────────┬──────────┘
        ┌─────────────────────┐      ┌─────────────────────┐                 │
        │   graph/exports/    │      │      wiki/          │                 │
        │   latest.graphml    │      │   *.md (entities)   │                 │
        │   (NetworkX)        │      │   auto + human      │                 │
        └──────────┬──────────┘      └──────────┬──────────┘                 │
                     │                          │                            │
                     └──────────────┬───────────┴────────────────────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   User receives     │
                         │   answer with       │
                         │   provenance        │
                         └─────────────────────┘
```

### Agent Responsibilities

| Agent | Role | Input | Output | Frequency |
|-------|------|-------|--------|-----------|
| **SupervisorAgent** | Orchestrate autonomous loop | System state + file events | Dispatch queue + health state | Continuous (configurable interval) |
| **ResearchAgent** | Fetch new papers from 7 sources | Research topics (YAML) | `raw/inbox/*.md`, `*.pdf` | APScheduler (per `sources.yaml`) |
| **PipelineRunner** | Process documents through 4 stages | `raw/inbox/` files | `ClaimCollection` JSON | On `ingest` or watchdog trigger |
| **GraphMaterializer** | Build knowledge graph from claims | `ClaimCollection` | `graph/exports/latest.graphml` | On `materialize graph` |
| **WikiMaterializer** | Generate wiki pages from claims+evidence | `ClaimCollection` + `EvidenceStore` | `wiki/*.md` | On `materialize wiki` |
| **QueryAgent** | Answer user questions with citations | User query | Answer + `[EVIDENCE:]`, `[WIKI:]`, `[GRAPH:]` markers | On `ask` command |

### Agent Communication Patterns

```
┌─────────────────────────────────────────────────────────────────┐
│                    SYNCHRONOUS (CLI-triggered)                  │
├─────────────────────────────────────────────────────────────────┤
│  llm-rag ingest ──▶ PipelineRunner ──▶ ClaimCollection          │
│  llm-rag ask ──▶ QueryAgent ──▶ (Claims + Wiki + Graph) ──▶ Answer │
│  llm-rag materialize graph ──▶ GraphMaterializer ──▶ GraphML   │
│  llm-rag materialize wiki ──▶ WikiMaterializer ──▶ Markdown    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    ASYNCHRONOUS (Scheduled)                     │
├─────────────────────────────────────────────────────────────────┤
│  SupervisorAgent (Phase 5):                                     │
│    APScheduler ──▶ ResearchAgent subagents ──▶ raw/inbox/      │
│    watchdog (file events) ──▶ PipelineRunner ──▶ ClaimCollection │
│    Heartbeat + health tracking ──▶ .supervisor/state.json       │
└─────────────────────────────────────────────────────────────────┘
```

### Materialization Commands

| Command | Description |
|---------|-------------|
| `llm-rag materialize graph` | Rebuild graph from ClaimCollection JSONs |
| `llm-rag materialize wiki` | Rebuild wiki pages from claims + evidence |
| `llm-rag materialize all` | Rebuild both graph and wiki |
| `llm-rag build-graph` | Alias for `materialize graph` |
| `llm-rag compile-wiki` | Alias for `materialize wiki` |

### Supervisor Loop (Phase 5)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SUPERVISOR LOOP (Phase 5)                            │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────┐   │
│  │  APScheduler │    │   watchdog   │    │     ShutdownManager         │   │
│  │              │    │              │    │                              │   │
│  │  Schedules   │    │  Monitors    │    │  SIGTERM/SIGINT/SIGHUP →    │   │
│  │  subagents   │    │  raw/inbox/  │    │  graceful drain + cleanup   │   │
│  │  per config  │    │  for new     │    │  30s timeout                │   │
│  │  (sources    │    │  files       │    │                              │   │
│  │   .yaml)     │    │              │    └──────────────────────────────┘   │
│  └──────┬───────┘    └──────┬───────┘                                      │
│         │                   │                                               │
│         ▼                   ▼                                               │
│  ┌──────────────────────────────────────┐                                   │
│  │         SupervisorAgent              │                                   │
│  │                                      │                                   │
│  │  - Heartbeat tracking (state.json)   │                                   │
│  │  - Error rate monitoring             │                                   │
│  │  - Subagent health tracking          │                                   │
│  │  - PID file management               │                                   │
│  └──────────────┬───────────────────────┘                                   │
│                 │                                                            │
│         ┌───────┴───────┐                                                   │
│         ▼               ▼                                                   │
│  ┌────────────┐  ┌──────────────┐                                          │
│  │ Research   │  │ Pipeline     │                                          │
│  │ Agent      │  │ Runner       │                                          │
│  │ (fetch)    │  │ (ingest)     │                                          │
│  └────────────┘  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Subagent scheduling** is driven by `config/sources.yaml`. Each subagent has an `enabled` flag and a `schedule` string (e.g., `interval:hours=12`). APScheduler dispatches enabled subagents at the configured intervals to fetch new papers matching your research topics.

**Health monitoring** aggregates three signals into an overall health status:
- **Heartbeat**: updated every cycle. <60s = HEALTHY, <300s = DEGRADED, >300s = UNHEALTHY
- **Error rate**: errors / (files_processed + errors). <10% = HEALTHY, <50% = DEGRADED, >50% = UNHEALTHY
- **Subagent health**: per-subagent tracking of consecutive failures and success rate

**Graceful shutdown**: the supervisor handles SIGTERM, SIGINT, and SIGHUP signals. On receiving a signal, it finishes the current cycle, drains pending work, cleans up the PID file, and exits within a 30-second timeout.

### Key V2 Principles

1. **Evidence is the source of truth** — All knowledge traces back to `EvidenceDocument` + `EvidenceChunk`
2. **Claims are first-class** — `EntityClaim`, `RelationClaim`, `Fact` are explicit schemas (not buried in graph/wiki)
3. **Graph & Wiki are projections** — Deterministically materialized from claims, rebuildable on demand
4. **Human sections preserved** — Wiki `human-start`/`human-end` blocks survive regeneration
5. **Backward compatible** — All existing CLI/MCP interfaces work unchanged

---

## Requirements

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **`ANTHROPIC_API_KEY`** — Claude API access ([get one](https://console.anthropic.com/))
- **`FIRECRAWL_API_KEY`** — for web/URL ingestion ([get one](https://firecrawl.dev/))
- `SERPAPI_KEY` — optional, enables GoogleScholarSubagent

**Disk space:** The `sentence-transformers` embedding model (~90 MB) is downloaded on first run. Chroma embeddings and GraphML snapshots grow with your corpus.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Ozzstein/Biblioteca.git
cd Biblioteca

# Install all dependencies (including dev tools)
uv sync --extra dev

# Verify
uv run python -c "import llm_rag; print('ok')"
uv run pytest tests/ -q
```

**Expected output:** `544 passed, 1 skipped`

---

## Configuration

**API keys** go in `.env` (never committed):

```bash
cp .env.example .env
# Edit .env:
# ANTHROPIC_API_KEY=***
# FIRECRAWL_API_KEY=***
# SERPAPI_KEY=*** optional
```

**Research topics** — edit `config/sources.yaml` to change what the system monitors:

```yaml
research_topics:
  - "LFP cycle life degradation"
  - "solid electrolyte interphase formation"
  - "silicon anode volume expansion"
  # add your own topics here
```

**Model assignments** — edit `config/settings.yaml` to change which Claude model handles each task. Default: Haiku for extraction (cost), Sonnet for synthesis, Opus for deep analysis.

**Entity normalization** — add aliases to `config/entity-normalization.yaml` as you encounter inconsistent naming in your corpus.

**Supervisor scheduling** — edit `config/sources.yaml` to control subagent schedules:

```yaml
subagents:
  arxiv:
    enabled: true
    schedule: "interval:hours=12"     # every 12 hours
  semantic_scholar:
    enabled: true
    schedule: "interval:hours=6"      # every 6 hours
  openalex:
    enabled: false                    # disabled — set true to activate
    schedule: "interval:days=1"
  # Format: "interval:<unit>=<value>" where unit is seconds/minutes/hours/days
```

**Health thresholds** (not user-configurable, defined in code):

| Signal | HEALTHY | DEGRADED | UNHEALTHY |
|--------|---------|----------|-----------|
| Heartbeat age | <60s | 60–300s | >300s |
| Error rate | <10% | 10–50% | >50% |
| Subagent consecutive failures | 0–3 | 4–5 | >5 |

---

## Troubleshooting (Supervisor)

| Problem | Solution |
|---------|----------|
| Supervisor won't start | Check `llm-rag supervisor status` — may already be running |
| Status shows DEGRADED/UNHEALTHY | Check `.supervisor/supervisor.log` for errors |
| Subagent failing repeatedly | Verify API keys in `.env`; check subagent health in status output |
| Want to pause a source | Set `enabled: false` in `config/sources.yaml` and restart supervisor |
| Logs location | `.supervisor/supervisor.log` (JSON format, rotated) |
| State/PID files | `~/.llm-rag/supervisor/state.json` and `supervisor.pid` |
| Force stop stale process | Delete `.supervisor/supervisor.pid` if process is already dead |

---

## Key Commands

### System & Diagnostics
```bash
uv run llm-rag status              # show config, API keys, corpus stats
```

### Document Processing
```bash
uv run llm-rag ingest                          # process all files in raw/inbox/
uv run llm-rag ingest --path raw/papers/paper.md
uv run llm-rag ingest --doc-id papers/paper-001
uv run llm-rag ingest --force                  # reprocess regardless of hash
uv run llm-rag pipeline run --path raw/papers/paper.md
uv run llm-rag pipeline run --force
```

### Query & Retrieval
```bash
uv run llm-rag ask "what causes LFP capacity fade?"
uv run llm-rag ask "compare LFP vs NMC cycle life" --mode hybrid --verbose
uv run llm-rag ask "dominant failure mechanisms in NMC811" --quality
```

### Supervisor (Phase 5)
```bash
uv run llm-rag supervisor start               # start autonomous loop (daemonizes)
uv run llm-rag supervisor start --interval 30  # poll every 30 seconds
uv run llm-rag supervisor start --foreground   # run in foreground (logs to console)
uv run llm-rag supervisor stop                 # send stop signal to running daemon
uv run llm-rag supervisor status               # show health, heartbeat, error rate
```

**Example output:**
```
# Start
Supervisor started (PID 264864).

# Already running
Supervisor is already running.

# Stop
Sent stop signal to supervisor (PID 264864).

# Status
Supervisor Status
────────────────────────────────────────
  Running:          yes
  PID:              264864
  Health:           [HEALTHY]
  Heartbeat:        1s ago
  Start time:       2026-04-24T17:01:05.336732+00:00
  Last heartbeat:   2026-04-24T17:01:05.336804+00:00
  Files processed:  0
  Errors:           0
  Error rate:       0.0%
  Pending files:    0
```

### Materialization (V2)
```bash
uv run llm-rag materialize graph              # rebuild graph from claims
uv run llm-rag materialize wiki               # rebuild wiki from claims + evidence
uv run llm-rag materialize all                # rebuild both
uv run llm-rag build-graph                    # alias for materialize graph
uv run llm-rag compile-wiki                   # alias for materialize wiki
```

---

## Project Structure

```
Biblioteca/
├── src/llm_rag/
│   ├── cli.py                 # Typer CLI (status, ingest, ask, pipeline, materialize)
│   ├── config.py              # Settings with env var overrides
│   ├── pipeline/
│   │   ├── runner.py          # Sequential stage execution + validation
│   │   ├── contracts.py       # 9 Pydantic models for typed interfaces
│   │   └── manifest.py        # Pipeline state tracking
│   ├── evidence/
│   │   └── models.py          # EvidenceDocument, EvidenceChunk, ProvenanceSpan
│   ├── knowledge/
│   │   └── models.py          # Claim, Fact, EntityClaim, RelationClaim
│   ├── graph/
│   │   ├── materializer.py    # Build graph from claims (V2)
│   │   ├── normalization.py   # Alias resolution, canonical IDs
│   │   └── store.py           # NetworkX persistence
│   ├── wiki/
│   │   ├── materializer.py    # Build wiki from claims+evidence (V2)
│   │   ├── reader.py          # Parse human/auto sections
│   │   └── writer.py          # Template-based page generation
│   ├── query/
│   │   └── agent.py           # Phased retrieval + citation-aware synthesis
│   ├── supervisor/
│   │   ├── loop.py            # SupervisorAgent — APScheduler + main cycle
│   │   ├── watcher.py         # watchdog FileSystemEventHandler for raw/inbox/
│   │   ├── state.py           # PID file, state.json, health tracking
│   │   └── shutdown.py        # Graceful shutdown (SIGTERM/SIGINT/SIGHUP)
│   ├── mcp/
│   │   ├── graph_io.py        # Graph MCP tools
│   │   ├── wiki_io.py         # Wiki MCP tools
│   │   └── corpus_io.py       # Vector store tools
│   └── utils/
│       ├── chunking.py        # Token-aware text splitting
│       ├── retry.py           # Exponential backoff decorator
│       ├── hashing.py         # Content deduplication
│       └── logging_config.py  # Structured logging (JSON file + console)
├── config/
│   ├── settings.yaml          # Model assignments, pipeline params
│   ├── sources.yaml           # Research topics to monitor
│   ├── entity-normalization.yaml  # Alias → canonical ID mappings
│   └── page-templates/        # 14 entity templates + _fallback.md
├── tests/                     # 544 tests (100% coverage target)
│   ├── evidence/              # Evidence schema tests
│   ├── knowledge/             # Claim/fact schema tests
│   ├── graph/                 # Materializer, normalization, provenance
│   ├── wiki/                  # Materializer, reader, writer
│   ├── query/                 # QueryAgent, citations
│   ├── pipeline/              # Contracts, runner, manifest
│   ├── supervisor/            # Supervisor loop, health, shutdown, state tests
│   └── test_cli.py            # CLI integration tests
└── docs/
    ├── architecture/
    │   └── current-runtime.md  # Truthful V1 runtime documentation
    └── roadmap.md             # V1/V2/V3 evolution plan
```

---

## Test Coverage

| Phase | Component | Tests | Key Deliverables |
|-------|-----------|-------|------------------|
| **Phase 0** | CLI Foundation | 20 | `status`, `ingest`, `ask`, `pipeline run` commands |
| **Phase 1** | Typed Contracts | 98 | 9 Pydantic models, 5 golden JSON fixtures |
| **Phase 2** | Knowledge Integrity | 51 | 14 wiki templates, graph normalization, provenance |
| **Phase 3** | Query Orchestration | 55 | Phased retrieval, citation markers, retry logic |
| **Phase 4** | V2 Internals | 156 | Evidence/claim schemas, materializers, rebuild commands |
| **Compat** | Backward Compatibility | 53 | All existing interfaces intact |
| **Total** | | **544** | Production-ready V2 foundation |

Run tests:
```bash
uv run pytest tests/ -q
# 544 passed, 1 skipped
```

---

## Roadmap

### ✅ Completed (Phases 0-5)
- [x] CLI with all core commands
- [x] Typed pipeline contracts with validation
- [x] Knowledge integrity (templates, normalization, provenance)
- [x] Multilayer query orchestration
- [x] V2 architecture (evidence → claims → projections)
- [x] Autonomous supervisor loop (APScheduler + watchdog)
- [x] Research subagent scheduling (arXiv, Semantic Scholar, PubMed, etc.)
- [x] Health monitoring (heartbeat, error rate, subagent health)
- [x] Graceful shutdown (SIGTERM/SIGINT/SIGHUP with 30s timeout)

### 🔄 Next (Phase 6+)
- [ ] Neo4j graph backend migration
- [ ] Web UI for query/browse
- [ ] Docker containerization

See full roadmap: [`docs/roadmap.md`](docs/roadmap.md)

---

## External Integrations

- **Writing-app examples:** [`examples/writing-app/`](examples/writing-app/) — Claude Desktop, Cursor, and Python reference clients for the Cloudflare-protected MCP gateway.
- **Gateway API contract:** [`docs/api/v1.md`](docs/api/v1.md) — stable v1.0.0 route, auth, citation, error, idempotency, and versioning contract for external clients.

---

## Developer Docs

- **Developer guide (start here):** [`CLAUDE.md`](CLAUDE.md) — complete reference for working with this codebase; covers all conventions, schemas, agent designs, and how-to guides
- **Current runtime architecture:** [`docs/architecture/current-runtime.md`](docs/architecture/current-runtime.md) — PipelineRunner, QueryAgent, MCP tools
- **Full design spec:** [`docs/superpowers/specs/2026-04-18-battery-research-os-design.md`](docs/superpowers/specs/2026-04-18-battery-research-os-design.md)
- **v1/v2/v3 Roadmap:** [`docs/roadmap.md`](docs/roadmap.md)

---

## License

MIT
