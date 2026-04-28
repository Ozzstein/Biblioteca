# Battery Research OS — Roadmap

**Last Updated:** April 28, 2026 (PM)
**Current Phase:** V2 — Lab Knowledge Extension Steps 1–5 SHIPPED; Step 6 (docs polish) remains
**Status:** Web Dashboard ✅ | Lab-doc ingest ✅ | Query Intent ✅ | Federated MCP gateway ✅ | Cloudflare Access auth ✅ | Writing-app reference clients ✅ | MCP-over-HTTP protocol bridge ✅ | v1 API spec ✅ | Documentation refresh ⏳ (Step 6) | Gap Analysis ⏳ (V3)

Latest milestone: PR #6 merged to `main` 2026-04-28 — `22a298f Merge pull request #6 from Ozzstein/Ozzstein/lab-knowledge-step5`. MCP-over-HTTP protocol bridge (FastMCP `streamable_http_app` mounted with Cloudflare Access ASGI middleware), three reference clients (Claude Desktop, Cursor, custom Python), expanded `docs/api/v1.md` (327 lines, semver + error model + citation payload + idempotency + streaming + timeouts), and all four Step 4 follow-ups closed. **740 passing tests.** Step 5 review verdict: `docs/review-step5.md`.

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

**Progress:** 7/8 V2 items complete (88%); Lab Knowledge Extension Steps 1–5 of 6 done. **Only V2 Step 6 (documentation refresh) remains in this milestone.**

| Item | Status | Notes |
|------|--------|-------|
| Web Dashboard | ✅ **DONE** | FastAPI + React, D3.js graph viz, 5 pages |
| Federated MCP Gateway | ✅ **DONE** (V2 Step 4, 2026-04-28) | `/mcp/*` over HTTP behind Cloudflare Access; per-source servers (literature, lab); restart-on-crash; filelock-guarded wiki writes; protocol v0.1 with conformance suite |
| Lab-doc Ingest (SOPs / meetings / internal reports) | ✅ **DONE** (V2 Step 2, 2026-04-28) | `Sop`/`Meeting`/`InternalReport` schemas with status + version + ingested_at; doc_type enum + alias-map validator; per-doc-type extraction prompts; SOP versioning layout |
| Query Intent Classification | ✅ **DONE** (V2 Step 3, 2026-04-28) | User-job intents (`reporting`/`know-how`/`insight`/`other`); confidence-threshold hybrid fallback; authority-precedence ranking |
| Cloudflare Access Authentication | ✅ **DONE** (V2 Step 4, 2026-04-28) | CF Access JWT validation on both gateway + dashboard; service tokens for machine clients; no bearer middleware |
| Writing-app Reference Clients | ✅ **DONE** (V2 Step 5, 2026-04-28 PM) | Claude Desktop, Cursor, custom Python with smoke test. `examples/writing-app/`. |
| MCP-over-HTTP Protocol Bridge | ✅ **DONE** (V2 Step 5 bonus, 2026-04-28 PM) | `POST /mcp` exposes a `query` tool over MCP streamable HTTP via FastMCP, mounted as a starlette route wrapped in custom `CloudflareAccessASGI` middleware. Unlocks real Claude Desktop / Cursor connectivity. |
| v1 API spec | ✅ **DONE** (V2 Step 5, 2026-04-28 PM) | `docs/api/v1.md`: 327 lines covering semver versioning, full error model with status+code table, citation payload format, per-endpoint idempotency, streaming behavior, timeout semantics, explicit out-of-scope list. Sister-project integration contract. |
| Documentation refresh | ⏳ TODO (V2 Step 6) | CLAUDE.md MCP-Gateway section, schema-types table updates, doc_type enum, per-source auto-section convention. C2/C3 from `docs/review-step5.md` may fold here. |
| Supervisor Gap Analysis | ⏳ TODO (V3) | Claude reads wiki/graph to identify missing knowledge |
| Google Scholar Subagent | ⏳ TODO | SerpAPI + Firecrawl fallback |
| Cross-document Deduplication | ⏳ TODO | Fuzzy title + abstract matching |
| Neo4j Integration | ⏳ TODO (V2.5) | Replace NetworkX, Cypher support. Threshold-gated: migrate when entity count > ~50k OR sister project federated graph queries become regular workload |
| Structured Observability | ⏳ TODO | Token usage, latency, error rates |
| Contradiction Flagging | ⏳ TODO (V2.5) | ReviewerAgent → GitHub issues |
| Federation v0.2 | ⏳ TODO (~1–2 months) | Sister experimental-data project will plug in via the v0.1 protocol; v0.2 finalizes any contract gaps surfaced during integration |

### Step 4 follow-ups — ALL CLOSED in Step 5

- **F1** ✅ — `docs/api/v1.md` expanded 99 → 327 lines.
- **F2** ✅ — dashboard CORS now reads `Settings.gateway_cors_origins`.
- **F3** ✅ — dashboard `/api/query` switched to `QueryPlanner` + `MCPPool.from_yaml`.
- **F4** ✅ — gateway uses `PROJECT_ROOT / "config" / "mcp-sources.yaml"`.

### Step 5 follow-ups (non-blocking, tracked in `docs/review-step5.md`)

- **C1** — citation `source` field is currently derived by `doc_id` string-prefix matching (sop/, meeting/, report/ → "lab"). Fragile. Should propagate the actual source-server name through the planner. v1.1 follow-up.
- **C2** — Claude Desktop config uses `enterpriseConfig.managedMcpServers` (MDM-managed format). Verify the deployment model used by the org; may need to ship both shapes (MDM + per-user `mcpServers`).
- **C3** — dashboard `/api/query` opens a fresh `MCPPool` per request (~seconds of cold-start latency). Should be lifespan-managed like the gateway. Fold into V2 Step 6.

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
- ~~Query intent classification: route queries to wiki-first, vector-first, graph-first, or hybrid retrieval based on intent~~ **✅ DONE in V2 Step 3** — user-job intents (`reporting`/`know-how`/`insight`/`other`) classified by Haiku; confidence-threshold hybrid fallback (A5A); authority-precedence ranking (CX-7) reads `status` field on entities
- ~~Separate QueryPlanner from retrieval/synthesis for testability and extensibility~~ **✅ DONE** — `src/llm_rag/query/planner.py`

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
