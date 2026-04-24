# Battery Research OS

An autonomous, local-first research assistant for battery R&D knowledge management. It continuously monitors research sources (arXiv, Semantic Scholar, PubMed, and more), ingests documents, extracts structured knowledge using Claude, maintains a human-readable markdown wiki, builds a NetworkX knowledge graph, and answers queries with full provenance citations — all running locally with no cloud storage required.

---

## Key Features

- **Autonomous monitoring**: Watches 6 research sources (arXiv, Semantic Scholar, OpenAlex, PubMed, Unpaywall, Firecrawl) on configurable schedules; new papers appear in `raw/` automatically
- **Multi-format ingestion**: PDFs (pdfplumber), markdown, URLs, DOIs, CSVs, meeting notes — drop files in `raw/inbox/` for instant processing
- **Structured extraction**: Claude Haiku extracts 14 entity types and 15 relation types from each document with per-chunk provenance records
- **Section-fenced wiki**: Markdown wiki with `auto` sections (machine-managed) and `human` sections (never overwritten) — you and the agents edit the same files safely
- **Knowledge graph**: NetworkX graph with JSON/GraphML persistence; Neo4j-ready schema for future migration
- **Phased query retrieval**: QueryAgent gathers context in three phases (evidence → wiki → graph), then synthesizes an answer with inline provenance citations
- **Full provenance**: Every claim, entity, and wiki section traces back to the source document, section, and page number
- **Battery-domain schema**: 14 entity types (Material, Cell, Claim, FailureMechanism...) and 15 relation types (USES_MATERIAL, CAUSES, MITIGATES...) tuned for battery R&D

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

**Query options:**
- `--quality` — use Opus for deep analysis
- `--verbose` — show retrieval trace and citations

---

## Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │         SupervisorAgent (APScheduler)         │
                    │  polls every 60s, dispatches pending work     │
                    └──────────────┬───────────────────────────────┘
                                   │ dispatches
             ┌─────────────────────┼──────────────────────┐
             │                     │                      │
             ▼                     ▼                      ▼
 ┌──────────────────┐   ┌────────────────────────┐  ┌──────────────────┐
 │  ResearchAgent   │   │     PipelineRunner     │  │  ReviewerAgent   │
 │  + Subagents     │   │  (sequential + retry)  │  │  (post-pipeline) │
 │                  │   │                        │  └──────────────────┘
 │  - arXiv         │   │  Stage 1: Ingestion    │
 │  - SemanticSchol.│   │  Stage 2: Extraction   │
 │  - OpenAlex      │   │  Stage 3: Normalization│
 │  - PubMed        │   │  Stage 4: Wiki Compile │
 │  - Unpaywall     │   │  Stage 5: Graph Update │
 │  - Firecrawl     │   └──────────┬─────────────┘
 └────────┬─────────┘              │
          │                        │ writes via MCP tools
          ▼                        ▼
     raw/inbox/       ┌────────────────────────────────────┐
     (drop zone)      │         Three Data Stores          │
                      │                                    │
                      │  wiki/        ← understanding      │
                      │  graph/       ← relations          │
                      │  retrieval/   ← evidence + vectors │
                      └────────────────────┬───────────────┘
                                           │
                      ┌────────────────────▼───────────────┐
                      │           QueryAgent                │
                      │  phased retrieval + synthesis       │
                      │  evidence → wiki → graph → answer   │
                      │                                     │
                      │  llm-rag ask "your question"        │
                      └─────────────────────────────────────┘
```

**Three data stores:**

| Store | Role | Format |
|---|---|---|
| `wiki/` | System of understanding | Plain markdown, human-editable |
| `graph/` | System of relations | NetworkX + JSON/GraphML |
| `raw/` + `retrieval/` | System of evidence | Raw files + Chroma vector store |

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
git clone <repo-url>
cd llm_rag

# Install all dependencies (including dev tools)
uv sync --extra dev

# Verify
uv run python -c "import llm_rag; print('ok')"
uv run pytest tests/ -v
```

---

## Configuration

**API keys** go in `.env` (never committed):

```bash
cp .env.example .env
# Edit .env:
# ANTHROPIC_API_KEY=sk-ant-...
# FIRECRAWL_API_KEY=fc-...
# SERPAPI_KEY=           # optional
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

---

## Key Commands

```bash
# Check system status and configuration
uv run llm-rag status

# Process documents
uv run llm-rag ingest                          # process raw/inbox/
uv run llm-rag ingest --path raw/papers/paper.md
uv run llm-rag ingest --doc-id papers/paper-001
uv run llm-rag ingest --force                  # reprocess regardless of hash

# Run the full pipeline on a specific path
uv run llm-rag pipeline run --path raw/papers/paper.md
uv run llm-rag pipeline run --force

# Ask questions against the knowledge base
uv run llm-rag ask "what causes LFP capacity fade?"
uv run llm-rag ask "compare LFP vs NMC cycle life" --mode hybrid --verbose
uv run llm-rag ask "dominant failure mechanisms in NMC811" --quality
```

**Note:** The autonomous supervisor loop (`llm-rag run`), source fetching (`fetch`), wiki compilation (`compile-wiki`), graph building (`build-graph`), and export commands are planned for future phases. Currently, use `ingest` and `pipeline run` to process documents manually.

---

## Developer Docs

- **Developer guide (start here):** [`CLAUDE.md`](CLAUDE.md) — complete reference for working with this codebase; covers all conventions, schemas, agent designs, and how-to guides
- **Current runtime architecture:** [`docs/architecture/current-runtime.md`](docs/architecture/current-runtime.md) — PipelineRunner, QueryAgent, MCP tools
- **Full design spec:** [`docs/superpowers/specs/2026-04-18-battery-research-os-design.md`](docs/superpowers/specs/2026-04-18-battery-research-os-design.md)
- **v1/v2/v3 Roadmap:** [`docs/roadmap.md`](docs/roadmap.md)
