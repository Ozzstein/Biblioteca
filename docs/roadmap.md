# Battery Research OS — Roadmap

**Last Updated:** April 27, 2026  
**Current Phase:** V2 — Hardening + Full Integrations  
**Status:** Web Dashboard ✅ COMPLETE | Query Intent ⏳ TODO | Gap Analysis ⏳ TODO

---

## V1 — Current Runtime (what exists now)

For full details, see [architecture/current-runtime.md](architecture/current-runtime.md).

**Orchestration:**
- **PipelineRunner** — sequential 5-stage document processor with retry and dead-letter handling (ingestion → extraction → normalization → wiki compile → graph update)
- **SupervisorAgent** — simple async loop with APScheduler for research subagent scheduling; polls for pending files every 60s
- **File watcher** — watchdog handler on `raw/inbox/` for drop-zone auto-detection

**Query:**
- **QueryAgent** — phased retrieval (evidence → wiki → graph) followed by Claude synthesis with inline provenance citations
- No query routing or intent classification; all queries follow the same pipeline
- `--quality` flag switches synthesis from Sonnet to Opus

**Data access:**
- Three FastMCP stdio servers (corpus_io, wiki_io, graph_io) provide all agent-to-store interactions
- MCPPool manages server process lifecycle across pipeline runs

**Agent execution:**
- Claude Code SDK-based agent runner with one-shot execution, Pydantic contract validation, and markdown prompt templates
- 6 research subagents (arXiv, Semantic Scholar, OpenAlex, PubMed, Unpaywall, Firecrawl)

**Not implemented (deferred to v2):**
- LangGraph or any graph-based orchestration
- Query intent classification or mode-based routing
- Neo4j integration
- ~~Web dashboard~~ **✅ DONE in V2** — See Infrastructure section above
- Structured observability

---

## V2 — Hardening + Full Integrations

**Goal:** Production-ready pipeline with all source connectors live, smarter knowledge synthesis, and graph DB connectivity.

**Phase 6 Progress:** 1/5 items complete (20%)

| Item | Status | Notes |
|------|--------|-------|
| Web Dashboard | ✅ **DONE** | FastAPI + React, D3.js graph viz, 5 pages |
| Query Intent Classification | ⏳ TODO | Route queries by intent (wiki/vector/graph/hybrid) |
| Supervisor Gap Analysis | ⏳ TODO | Claude reads wiki/graph to identify missing knowledge |
| Google Scholar Subagent | ⏳ TODO | SerpAPI + Firecrawl fallback |
| Cross-document Deduplication | ⏳ TODO | Fuzzy title + abstract matching |
| Neo4j Integration | ⏳ TODO (V2.5) | Replace NetworkX, Cypher support |
| Structured Observability | ⏳ TODO | Token usage, latency, error rates |
| Contradiction Flagging | ⏳ TODO (V2.5) | ReviewerAgent → GitHub issues |

### Source Connectors
- GoogleScholarSubagent: live SerpAPI integration with fallback to Firecrawl
- ElsevierSubagent: ScienceDirect full-text API (requires institutional or personal API key)
- PubMed: full MeSH term search, not just keyword
- Citation monitoring: Semantic Scholar citation graph — automatically fetch papers that cite key papers already in corpus

### Knowledge Pipeline
- Supervisor gap analysis: Claude-driven identification of wiki gaps rather than heuristic (empty Evidence sections). Supervisor reads the wiki and graph, identifies missing knowledge, generates targeted search queries for ResearchAgent.
- Cross-document deduplication: fuzzy title + abstract matching to prevent near-duplicate papers cluttering the corpus
- Smarter normalization: fine-tuned alias resolution using accumulated entity-normalization.yaml entries from v1 usage

### Graph
- Neo4j live connection: swap NetworkX runtime for Neo4j while keeping JSON exports as source of truth. Full Cypher query support.
- Graph-driven recommendations: "you have 5 papers on LFP degradation but no wiki page — create one?"

### Query
- Query intent classification: route queries to wiki-first, vector-first, graph-first, or hybrid retrieval based on intent (mechanistic, evidence, relational, synthesis)
- Separate QueryPlanner from retrieval/synthesis for testability and extensibility

### Infrastructure
- ~~Web dashboard~~: **✅ DONE** — FastAPI + React dashboard with corpus stats, graph visualization (D3.js), wiki index, processing queue status
  - 5 pages: Status, Corpus, Wiki, Graph, Query
  - Interactive D3.js force-directed graph with draggable nodes, color-coded entity types
  - Live API endpoints: `/api/health`, `/api/status`, `/api/corpus/*`, `/api/wiki/*`, `/api/graph/*`, `/api/query`
  - Dark theme, responsive design, hot reload in dev mode
  - Deployed at `http://<VPS-IP>:5173`
- Structured logging + observability: per-agent token usage, latency, error rates
- Automated contradiction flagging: ReviewerAgent runs on a schedule, files contradictions as GitHub issues or wiki tasks

---

## V3 — Goal-Directed Autonomous Research (Roadmap C)

**Goal:** The system moves from reactive (process what arrives) to proactive (pursue research goals, fill knowledge gaps, generate insights).

### Gap-Directed Search
- SupervisorAgent reads the wiki and knowledge graph, identifies what is *missing or underspecified*, and generates targeted search queries for ResearchAgent without human input
- Example: LFP material page exists but has no data on thermal runaway → Supervisor generates "LFP thermal runaway mechanisms" query and dispatches ResearchAgent

### Hypothesis Generation
- ResearchAgent proposes research hypotheses based on graph structure — patterns of relations that suggest unexplored connections
- Example: Material A CAUSES FailureMechanism X in context B, but no papers test Material A in context C → flag as hypothesis

### Contradiction Resolution
- Dedicated ContradictionAgent identifies when two claims in the corpus directly contradict each other
- Agent proposes what experimental conditions or methodological differences could explain the discrepancy
- Unresolved contradictions are surfaced as open questions in the wiki

### Cross-Paper Synthesis
- SynthesisAgent identifies when N papers together support a new higher-order claim not stated in any individual paper
- Generates draft synthesis wiki pages with explicit provenance chains
- Human reviews and approves before promotion to wiki

### Scheduled Intelligence Reports
- Weekly "state of knowledge" reports per research topic
- Automatically generated from wiki + graph, summarizing what's new, what's changed, what's still unknown
- Delivered as wiki pages + optional email/Slack digest

### Agent Memory & Self-Improvement
- Agents accumulate feedback on extraction quality, relevance scoring accuracy, and wiki page quality
- Normalization rules in `entity-normalization.yaml` are updated automatically when agents encounter consistently misresolved entities
- Relevance threshold auto-tuned based on which fetched papers actually contributed knowledge to the wiki
