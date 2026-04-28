# V2 Lab-Knowledge Extension + Federated MCP Gateway

**Date:** 2026-04-27
**Status:** APPROVED — ready to implement
**Branch:** `Ozzstein/lab-knowledge` (to be created from `origin/main` @ `90a783f`)
**Reviews:** `/office-hours` 2026-04-27, `/plan-eng-review` 2026-04-27 (CLEAR), Codex outside-voice 2026-04-27 (issues_found, all resolved)

This is the single source of truth for the V2 lab-knowledge work. It combines the design doc, the implementation plan, and the engineering-review verdict. If anything in `~/.claude/plans/replicated-soaring-teacup.md` or `~/.gstack/projects/Ozzstein-Biblioteca/ozzstein-lab-knowledge-design-20260427-155918.md` disagrees with this file, this file wins.

---

## 1. Context

Battery Research OS today processes published literature (papers, web pages, patents) through the existing 5-stage pipeline (ingest → extract → normalize → wiki → graph) and answers queries via a single phased retrieval (evidence → wiki → graph) followed by Claude synthesis. It has a localhost-only FastAPI dashboard (`web/api/main.py`, 549 lines) and three stdio-only MCP servers (`corpus_io`, `wiki_io`, `graph_io`) managed by `MCPPool` (`src/llm_rag/mcp/pool.py:62-224`).

Three capability gaps block its use as a real lab knowledge store:

1. **Lab paperwork is invisible.** SOPs, internal reports, meeting notes, and bureaucratic workflows currently sit in shared drives. The pipeline accepts them via `raw/inbox/` but treats them identically to research papers — same extraction prompt, same templates, no procedural awareness. The existing `_infer_doc_type()` (`runner.py:307-309`) captures the doc type but no downstream stage uses it.
2. **No external agentic access.** MCP servers run as local subprocess pipes; FastAPI is defined but never network-bound. A separate writing application or downstream agent cannot query the corpus, wiki, or graph remotely.
3. **No query intent.** Queries route through one path. A "summarize what we know about X" report request, a "find our SOP for Y" know-how query, and a "what trends across our last batch" insight query all hit the same generic synthesis. Reporting is mediocre, know-how lookups are slow, insight queries don't traverse the graph.

The user is one of several managers at a battery R&D org who would use this directly. Today, when they need any of insight / know-how / report, the answer is "manual, unstandardized." The most painful of the three is **reporting** — a 3-page internal report combining cycling results with literature currently takes 1–2 days of manual cut/paste/citation.

Adoption / cost is explicitly not the constraint for this project. The user has buy-in and wants the cutting-edge build.

## 2. Goals

1. Ingest lab paperwork (SOPs, meetings, internal reports) as first-class typed knowledge with versioning, status, and authority semantics.
2. Expose the knowledge store to external agentic clients (writing apps, custom agents) via MCP-over-HTTP behind a real auth boundary.
3. Route queries by user-job intent (`reporting | know-how | insight | other`) so each gets the appropriate retrieval shape and synthesis strategy.
4. Lay the federation substrate so the future sister experimental-data project (ETA 1–2 months) plugs in via a versioned protocol contract instead of being retrofitted.

## 3. Non-goals (NOT in scope)

- Raw experimental data ingestion → sister project (1–2 months); will federate via the v0.1 protocol when ready.
- Neo4j migration → V2.5, threshold-gated (entity count >50k OR sister project's federated graph queries become regular workload).
- Multi-user auth, audit log, per-user permissions → V3 (Cloudflare Access user identity is captured in headers; full audit/RBAC is later).
- Real-time collaborative editing of wiki pages.
- Public OSS release / external distribution.
- Mobile UX.
- Fine-tuned models.
- **Reporting templates / cite_pack / draft_section MCP tools** — assembly is the writing app's job (decision CX1B).
- **Shared-drive filesystem-watch connector** — TODO-1, defer until lab corpus is real and staleness pain hits.
- **End-to-end report-task eval suite** — TODO-2, defer until Step 5 ships and there's a baseline.
- **LRU query cache** — TODO-3, defer until repeat-query usage patterns settle.

All TODOs above are tracked in `TODOS.md` at the repo root.

## 4. Premises (agreed during /office-hours)

1. Reporting is the demo, not the only feature. Insight + know-how + reporting share a query layer with intent routing; reporting is the showpiece because the value is visible.
2. Lab paperwork is a first-class data source with typed schemas and dedicated templates, not "another doc folder."
3. External access = MCP-over-HTTP with auth, not a fresh REST API. Writing apps call the same MCP tools the internal pipeline uses.
4. Current 5-stage pipeline + 14 entity types are the right substrate. Extend, don't rewrite.
5. Cutting-edge means: query intent classification, gap-directed search, contradiction detection (V2/V3 roadmap items). Lab data + external access unblock these from being merely academic.

## 5. Approaches considered (one-line summary)

- **Approach A** — Sequential extension over 3 PRs (~3–4 weeks). No federation story; sister-project integration becomes a retrofit. **Rejected** because the user explicitly chose cutting-edge and the sister project is only 1–2 months out.
- **Approach C** — V2 query layer first, MCP gateway second; federation deferred. **Rejected** for the same reason.
- **Approach B (chosen)** — Federated MCP knowledge gateway. Per-source MCP servers + a gateway that classifies query intent, fans out, and merges. Future sister-project integration is a config entry, not a refactor.

The full alternatives discussion is preserved in the office-hours design doc at `~/.gstack/projects/Ozzstein-Biblioteca/ozzstein-lab-knowledge-design-20260427-155918.md` for historical reference.

## 6. Recommended approach (Approach B, eng-review-amended)

Refactor the three monolithic stdio MCP servers into separate per-source servers (literature, lab, plus the future sister source). Add a gateway that owns query-intent classification, source-fan-out, reranked merge, and synthesis with multi-source provenance. Expose the gateway over HTTP behind Cloudflare Access for both human (dashboard) and machine (writing-app) clients.

### 6.1 Dataflow diagram

```
                      +------------------------------------------------+
                      |          External clients                      |
                      |  (Claude Desktop, Cursor/Continue,             |
                      |   custom Python agent — Step 5)                |
                      +----------------+-------------------------------+
                                       | HTTPS + CF-Access-Client-Id/Secret
                                       v
                      +------------------------------------------------+
                      |         Cloudflare Edge (CX16A + A4A)          |
                      |  * Service-token validation (machines)         |
                      |  * SSO / IP allowlist (humans -> dashboard)    |
                      |  * TLS termination                             |
                      +----------------+-------------------------------+
                                       | Tunnel (cloudflared)
                                       v
        +------------------------------------------------------------------+
        |                 On-prem / VPS host                               |
        |                                                                  |
        |  +-------------------------+    +-------------------------+      |
        |  |  Dashboard FastAPI      |    |  Gateway FastAPI         |     |
        |  |  (web/api/main.py)      |    |  (mcp/gateway.py)        |     |
        |  |  -- humans, read-only   |    |  -- agents, /mcp/* + query|    |
        |  +------------+------------+    +-------------+------------+     |
        |               |  reads                         |  CF JWT trust   |
        |               v                                v                 |
        |  +------------------------+    +------------------------------+  |
        |  |  Read-only views       |    |  Query Planner (Step 3)      |  |
        |  |  of corpus/wiki/graph  |    |   intent: reporting|know-how |  |
        |  +------------------------+    |           |insight|other      | |
        |                                |   conf < 0.7 -> hybrid (A5A) |  |
        |                                |   authority precedence (CX-7)|  |
        |                                +-------------+----------------+  |
        |                                              | MCP tool calls    |
        |                                              v                   |
        |                              +------------------------------+    |
        |                              |  MCPPool (pool.py)            |   |
        |                              |  * spawn N from registry      |   |
        |                              |  * restart on crash w/ backoff|   |
        |                              |    (A3A)                      |   |
        |                              +-----+----------+----------+---+   |
        |                                    | stdio    | stdio    | HTTP  |
        |                                    v          v          v       |
        |                              +---------+ +---------+ +--------+  |
        |                              |literature| |  lab   | | sister |  |
        |                              | source   | | source | | source |  |
        |                              | (papers) | | (SOPs, | | (exp-  |  |
        |                              |          | | mtg,   | | data,  |  |
        |                              |          | | rpts)  | | later) |  |
        |                              +-----+----+ +---+----+ +--------+  |
        |                                    |         |                   |
        |                                    |         | filelock-guarded  |
        |                                    v         v wiki writes       |
        |                              +-----------------------------------+|
        |                              |   Shared canonical wiki + graph   ||
        |                              |   per-source auto-sections (A1B)  ||
        |                              |   freshness metadata (CX13B):     ||
        |                              |   ingested_at, source_url         ||
        |                              +-----------------------------------+|
        +------------------------------------------------------------------+
```

### 6.2 Federation contract (v0.1)

The federation contract is **versioned**, not frozen. Sister project builds against `v0.1` + the conformance suite + the `MockSource` reference implementation. Breaking changes bump to `v0.2` with a documented compatibility window.

Components:

- `docs/mcp-source-protocol-v0.1.md` — versioned spec doc
- `config/mcp-sources.yaml` — registry; each source declares its `capabilities` (which intents/tools it supports) and `version` it implements
- `tests/contracts/` — conformance test suite that any source must pass
- `src/llm_rag/mcp/sources/mock.py` — reference `MockSource` implementation that the sister project (and our own contract tests) build against

## 7. Locked decisions (from /plan-eng-review and Codex outside-voice)

13 explicit user decisions + 9 folded amendments + 2 known risks. All resolved; 0 unresolved.

### 7.1 Architecture

| ID | Decision | Effect |
|----|----------|--------|
| **1B** | Keep separate stdio source-server processes from day one | Plan as written, not collapsed to single-process |
| **A1B** | Cross-source wiki entities use **shared canonical pages with per-source auto-section names** (`evidence-literature`, `evidence-lab`, etc.) | Wiki section-fence convention extended; each source only writes its own named sections; synthesis merges at query time |
| **A3A** | `MCPPool` gains **restart-on-crash with exponential backoff** (1s, 2s, 4s, 8s, max 5 retries) | After max retries, source marked `unavailable`; gateway returns degraded responses with a warning naming the missing source. ~50 lines added to `pool.py` |
| **A4A** | **Cloudflare Access required** for production deployment (IP allowlist as floor, SSO if Zero Trust available) | Documented in deploy README |
| **A5A** | Query intent classifier gains **confidence-thresholded fallback to hybrid** when classifier confidence < 0.7 | Avoids silent mis-routes on borderline queries |
| ~~A2C~~ | ~~Bearer auth on dashboard with token-entry login UI~~ | **SUPERSEDED by CX16A** |

### 7.2 Code quality

| ID | Decision | Effect |
|----|----------|--------|
| **C1A** | Per-doc-type extraction prompts: `agents/prompts/extraction-{paper,sop,meeting,report}.md` with shared boilerplate at `agents/prompts/_extraction-shared.md` included via simple template substitution | Replaces "branch by doc_type" in one file |
| **C2A** | `DocumentManifest.doc_type` enum migration uses Pydantic `@field_validator` with an alias map (`papers → DocType.PAPER`, etc.); unknown strings fall through to `DocType.UNKNOWN` | No filesystem migration script needed; existing manifests load cleanly |
| **C3** (fold) | SOP files carry YAML frontmatter (`sop_id`, `version`, `effective_date`, `supersedes`); IngestionAgent reads via existing `python-frontmatter`; ExtractionAgent populates the Sop entity; GraphCuratorAgent updates the prior version's `superseded_by` field | Linkage mechanism specified |

### 7.3 Tests

| ID | Decision | Effect |
|----|----------|--------|
| **T1A** | Pre-refactor record/replay snapshot suite — capture ~20 representative MCP tool calls from today's monolithic servers to JSON fixtures BEFORE Step 1 begins; replay against new source servers; assert byte-equivalent | Catches regressions the existing test suite would miss |
| **T2A** | Ship a minimal eval harness with the plan — new `evals/` directory; per-prompt JSONL golden sets; `pytest`-runnable harness invokes Claude via the existing `agent_runner`; computes match scores; CI runs evals on PRs touching `agents/prompts/**` | Prompt regressions become test failures, not silent quality loss |

### 7.4 Performance

| ID | Decision | Effect |
|----|----------|--------|
| **P1B** | VPS is interim; long-term home is on-premise private server | Memory budget concerns dropped; provision generously |

### 7.5 Cross-model (Codex outside voice)

| ID | Decision | Effect |
|----|----------|--------|
| **CX1B** | Plan ships retrieval, not reporting assembly | Reporting templates / cite_pack / draft_section live in the writing app, not the gateway |
| **CX2A** | Proceed despite no experimental data in scope | Bet on substrate value; sister project plugs in 1–2 months |
| **CX4A** | Federation contract = **v0.1 semver** with capability negotiation, conformance test suite at `tests/contracts/`, and a `MockSource` reference implementation | Sister project builds against versioned contract, not "frozen" docs |
| **CX12A** | Use `filelock` library for per-file `FileLock` around every wiki page read-modify-write | New dep on `filelock`; wraps wiki writer to serialize concurrent writes from separate source-server processes |
| **CX13B** | Freshness metadata: each lab-doc entity gains `ingested_at` and `source_url` fields; synthesis surfaces "this is from <date> — verify against current source if critical" in citations | Surfaces staleness pain visibly without building the connector |
| **CX16A** | **Auth pivot to Cloudflare Access primitives end-to-end. SUPERSEDES A2C.** Drop the bearer-token middleware from FastAPI. Dashboard humans use Cloudflare Access user auth (SSO / email magic link / IP allowlist) — no login UI. Writing apps use Cloudflare Access **service tokens** (auto-rotated, per-client, revocable from Cloudflare dashboard) — `CF-Access-Client-Id` + `CF-Access-Client-Secret` headers. FastAPI trusts the headers and validates against Cloudflare's JWT | One env-var-secret category eliminated (`MCP_BEARER_TOKEN` no longer needed) |

### 7.6 Folded without further questions

- **A6** — ASCII dataflow diagram (above in §6.1)
- **A7** — SOP "current version" via `wiki/sop/<id>/index.md` frontmatter (`current_version: v3`), NOT symlinks (Windows portability)
- **CX-3** — Query intents renamed to user-job-aligned names: `reporting | know-how | insight | other`, with internal mapping to backend retrieval strategies (`synthesis | wiki+vector | graph+vector | hybrid`)
- **CX-6** — Entity resolution: extend existing `config/entity-normalization.yaml` with internal alias categories (SOP IDs, project codenames, internal nicknames)
- **CX-7** — Authority/precedence model for synthesis: each entity gets a `status` field (`approved | draft | superseded | unknown`); synthesis precedence: approved-internal > draft-internal > recent-meeting-decision > literature
- **CX-8** — Versioning fields extended to Meeting + InternalReport: `status (draft|final)`, `effective_date`, `superseded_by`
- **CX-9** — Ship `docs/api/v1.md` with stable request/response schema, citation payload format, streaming behavior, timeout semantics, error model, versioning policy
- **CX-14/15** — Add Step 0a (corpus curation) — manual user work — label ~20 SOPs, ~10 meetings, ~10 reports, ~10 reporting tasks → golden eval set; gates Step 3 evals
- **CX-18** — Drop `dataset` from doc_type enum (experiments are out of scope); re-add when sister project ships

### 7.7 Accepted as known risks (no plan change)

- **CX-19** — Neo4j deferral may underestimate cross-source impact when migration eventually happens
- **CX-20** — MCP federation is a tool-call plane; sister project may need a structured-analytics plane. Will be re-evaluated when sister project's actual query patterns are known

## 8. Open items resolved during /office-hours

| # | Question | Resolution |
|---|----------|------------|
| 1 | Writing-app target | All three: Claude Desktop + IDE-style (Cursor/Continue) + custom Python agent |
| 2 | Auth model | Cloudflare Access end-to-end (per CX16A); single bearer model dropped |
| 3 | TLS terminator | **Cloudflare Tunnel** — no inbound port exposure on the host; install `cloudflared`, point at `localhost:8443`, get a stable hostname |
| 4 | SOP versioning | Preserve old. Sop schema includes `version`, `effective_date`, `supersedes`, `superseded_by`, `deprecated`, `status`. Wiki layout: `wiki/sop/<sop_id>/v<version>.md` per version, `wiki/sop/<sop_id>/index.md` with `current_version` frontmatter resolving "current" |
| 5 | Gateway reachability | Cloudflare Tunnel + Cloudflare Access (CX16A). No direct host port exposure; two layers of defense (network edge + identity-provider auth) |
| 6 | Sister experimental-data project ETA | 1–2 months. Confirms Approach B (federated gateway from day one). Federation contract v0.1 must be published in Step 1 so the sister team can build to it in parallel |

## 9. Step-by-step execution plan

```
Step 0  -- Branch + CLAUDE.md skill routing block
Step 0a -- Corpus curation (manual; user labels ~50 docs as eval golden set)  [PARALLEL]
Step 1  -- MCP source-server refactor (T1A snapshot first)
        +  Protocol v0.1 spec (CX4A) + conformance suite + MockSource
Step 2  -- Typed lab-doc ingest
        +  Sop/Meeting/InternalReport schemas with status + version + effective_date + superseded_by (CX-8)
        +  Per-doc-type extraction prompts (C1A) + frontmatter linkage (C3)
        +  Wiki templates (sop, meeting, internal-report)
        +  entity-normalization.yaml internal-alias extension (CX-6)
        +  Freshness metadata (CX13B): ingested_at, source_url on entities
        +  doc_type enum + alias-map validator (C2A); 'dataset' DROPPED (CX-18)
Step 3  -- Query intent classifier
        +  User-job intent names (CX-3): reporting | know-how | insight | other
        +  Confidence-threshold hybrid fallback (A5A)
        +  Authority/precedence in synthesis (CX-7)
Step 4  -- MCP-over-HTTP gateway (no bearer middleware per CX16A)
        +  filelock around wiki writes (CX12A)
        +  Restart-on-crash with backoff (A3A)
        +  CF Access JWT validation
Step 5  -- Reference writing-app integrations (3 clients) + docs/api/v1.md (CX-9)
Step 6  -- Documentation updates (CLAUDE.md, docs/roadmap.md)
```

### Step 0 — Branch + onboarding cleanup

The repo is currently in detached-HEAD state on `origin/main` @ `90a783f`.

- Create branch `Ozzstein/lab-knowledge` from `origin/main`.
- Append the gstack skill-routing block to `CLAUDE.md` (approved during /office-hours onboarding, deferred due to plan mode):
  ```markdown
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
  ```
- Commit as `chore: add gstack skill routing rules to CLAUDE.md`.

### Step 0a — Corpus curation (manual, parallel)

Manual user work; no code conflict. Label ~50 docs from your existing or to-be-ingested lab corpus:

- ~20 SOPs (mix of approved, draft, superseded)
- ~10 meeting notes (mix of decisions, action items)
- ~10 internal reports (mix of cycling, EIS, post-mortem)
- ~10 reporting-task fixtures: "draft a report on X" + the ideal output a manager would produce manually

These become the golden eval set for Step 3 (intent classifier benchmark) and the per-prompt evals (T2A). Without this, the evals are vapor (Codex critique #15).

Output: `evals/golden/{sops,meetings,reports,reporting-tasks}/*.{md,json}` plus a manifest.

### Step 1 — MCP source-server refactor + protocol v0.1

The substrate move. After this step every external behavior is identical to today, but the MCP layer is structurally ready for federation.

**Prerequisite (T1A):** Capture ~20 representative MCP tool calls from today's monolithic servers to JSON fixtures BEFORE any refactor work. Script at `tests/snapshots/capture.py`. Snapshots live at `tests/snapshots/fixtures/`.

Critical files:

- `src/llm_rag/mcp/corpus_io.py` — split conceptually into `src/llm_rag/mcp/sources/literature.py` (Chroma + paper-chunk surface) plus generic helpers in `src/llm_rag/mcp/utils/io.py`. Keep tool names identical so existing pipeline code continues to call them by name.
- `src/llm_rag/mcp/wiki_io.py` and `src/llm_rag/mcp/graph_io.py` — refactor into per-source view layers. For Step 1, the lab source is empty; literature owns everything. Cross-source merging is Step 4's gateway concern.
- `src/llm_rag/mcp/pool.py` — extend `MCPPool` (lines 62-224) to spawn N source servers from `config/mcp-sources.yaml`. Add restart-on-crash with backoff (A3A) — exponential 1s, 2s, 4s, 8s, max 5 retries → mark source `unavailable`; subsequent calls return a "source unavailable" sentinel that the gateway turns into a degraded-response warning.

Federation contract deliverables (CX4A):

- `docs/mcp-source-protocol-v0.1.md` — semver protocol spec with capability negotiation rules
- `config/mcp-sources.yaml` schema:
  ```yaml
  protocol_version: "0.1"
  sources:
    - name: literature
      backend: stdio
      command: ["python", "-m", "llm_rag.mcp.sources.literature"]
      capabilities: ["tool:search_chunks", "tool:get_chunks", "intent:reporting", "intent:know-how", "intent:insight"]
    - name: lab
      backend: stdio
      command: ["python", "-m", "llm_rag.mcp.sources.lab"]
      capabilities: ["tool:search_chunks", "tool:get_chunks", "intent:reporting", "intent:know-how", "tag:sop", "tag:meeting", "tag:report"]
  ```
- `tests/contracts/` — conformance test suite: any source registered in `mcp-sources.yaml` must pass these tests.
- `src/llm_rag/mcp/sources/mock.py` — reference `MockSource` implementation that always passes the contract tests; sister project uses this as a starting point.

Tests:

- Replay T1A snapshot suite — assert byte-equivalent responses across all captured tool calls.
- New: `tests/mcp/test_pool_spawn_n.py` — config-driven spawn-N pattern.
- New: `tests/mcp/test_pool_restart.py` — kill subprocess mid-call, assert backoff retry sequence + eventual unavailability.
- New: `tests/contracts/test_mock_source.py` — MockSource passes the conformance suite.
- Existing 38 tests must pass unchanged.

### Step 2 — Typed lab-doc ingest

Add the lab knowledge source as a real typed citizen.

Critical files:

- `src/llm_rag/schemas/entities.py` — add `Sop`, `Meeting`, `InternalReport` Entity subclasses parallel to existing `Material`/`Cell`/`Claim` (lines 57-75). All three carry `status: Literal["approved","draft","superseded","unknown"]`, `effective_date`, `superseded_by`, `ingested_at` (CX13B), `source_url` (CX13B).
  - `Sop` adds: `sop_id`, `version`, `supersedes`, `procedure_steps[]`, `equipment[]`, `safety_notes`, `scope`, `deprecated: bool`
  - `Meeting` adds: `attendees[]`, `decisions[]`, `action_items[]`
  - `InternalReport` adds: `report_id`, `authors[]`, `period_covered`, `key_metrics`
- `src/llm_rag/schemas/provenance.py` — change `DocumentManifest.doc_type` (line 48) to typed enum: `paper | sop | report | meeting | unknown` (`dataset` dropped per CX-18). Pydantic `@field_validator` alias map per C2A:
  ```python
  _ALIAS_MAP = {"papers": DocType.PAPER, "sop": DocType.SOP, "reports": DocType.REPORT, "meetings": DocType.MEETING}
  @field_validator("doc_type", mode="before")
  def _resolve_alias(cls, v): return _ALIAS_MAP.get(v.lower(), DocType.UNKNOWN) if isinstance(v, str) else v
  ```
- `src/llm_rag/pipeline/runner.py:307-309` — `_infer_doc_type()` returns the enum.
- `agents/prompts/_extraction-shared.md` — shared boilerplate (battery taxonomy, output JSON schema, citation rules).
- `agents/prompts/extraction-paper.md` (extracted from existing `extraction.md`), `extraction-sop.md`, `extraction-meeting.md`, `extraction-report.md` — each branches via simple template substitution to include the shared block. ExtractionAgent loads the file matching `manifest.doc_type` (per C1A).
- `config/page-templates/sop.md`, `meeting.md`, `internal-report.md` — new templates following the existing section-fence convention. SOP template includes versioning header consumed by the wiki reader.
- `config/entity-normalization.yaml` — add internal alias categories: `sop_aliases`, `project_codenames`, `internal_nicknames` (CX-6).
- `src/llm_rag/mcp/sources/lab.py` — new MCP source server registered in `config/mcp-sources.yaml`. Owns Chroma collection scoped to lab docs, lab wiki pages, lab graph slice.
- Wiki SOP layout: `wiki/sop/<sop_id>/v<version>.md` per version, plus `wiki/sop/<sop_id>/index.md` with frontmatter:
  ```yaml
  ---
  sop_id: SOP-001
  current_version: v3
  versions: [v1, v2, v3]
  ---
  ```
  Wiki reader resolves "current" by reading `index.md.current_version` (NOT symlinks per A7).

Cross-source wiki naming convention (A1B): every auto-section that varies by source MUST be suffixed with the source name, e.g., `<!-- auto-start: evidence-literature -->` and `<!-- auto-start: evidence-lab -->`. Each source server only writes its own named sections. Update `src/llm_rag/wiki/writer.py` and `reader.py` to enforce and merge.

Tests:

- `tests/pipeline/test_sop_ingest.py` — happy path, frontmatter-less SOP, malformed YAML, idempotency, manifest stage gating.
- `tests/pipeline/test_meeting_ingest.py`, `test_internal_report_ingest.py`.
- `tests/schemas/test_doc_type_enum.py` — every alias maps correctly; unknown → DocType.UNKNOWN; existing manifest fixtures load. **REGRESSION CRITICAL.**
- `tests/wiki/test_per_source_sections.py` — both literature and lab write their named sections to `wiki/materials/lfp.md` without collision; reader merges both.
- `tests/wiki/test_sop_versioning.py` — v2 over v1 → entities linked, index.md updated, default query returns v2, `--include-history` returns both.

### Step 3 — Query intent classification

Implement the V2 roadmap "Query Intent Classification" item with user-job intent names.

Critical files:

- `src/llm_rag/query/planner.py` — new module. Stdlib state machine (NOT LangGraph — `langgraph` is not in `pyproject.toml`; don't spend an innovation token here). Classifier uses `model_relevance_scoring` (Haiku) to assign user-job intent + confidence:
  - intents: `reporting | know-how | insight | other`
  - returns `{"intent": "...", "confidence": 0.0–1.0}`
- `src/llm_rag/query/retrieval.py` — implement four routes mapped from intents:
  - `reporting` → hybrid (parallel fan-out across all sources, all retrieval modes, reranked)
  - `know-how` → wiki-first scan + vector follow-up
  - `insight` → graph-first traversal + vector follow-up
  - `other` (or low confidence per A5A) → hybrid
- `src/llm_rag/query/answer.py` — synthesis with multi-source provenance citations + authority precedence (CX-7): rerank chunks by `(status weight, recency, source-trust)` before passing to Sonnet. Each retrieved chunk/page/path carries provenance forward.
- `src/llm_rag/cli.py` — add `--mode {reporting,know-how,insight,hybrid,auto}` flag. `auto` uses the classifier.
- `agents/prompts/intent-classifier.md` — new prompt. Returns JSON `{intent, confidence}` strictly.

Tests:

- `tests/query/test_planner.py` — 20-query benchmark from `evals/golden/reporting-tasks/`; assert classifier ≥80% intent match.
- `tests/query/test_confidence_threshold.py` — confidence < 0.7 → hybrid fallback; boundary case (= 0.7); classifier API failure → hybrid fallback.
- `tests/query/test_authority_precedence.py` — when literature and SOP disagree on a fact, the SOP wins in synthesis output if its `status == "approved"`.

### Step 4 — MCP-over-HTTP gateway

The external-agent-access piece. This is what unlocks the writing-app integration.

Critical files:

- `src/llm_rag/mcp/gateway.py` — new FastAPI app. Wraps the source MCP servers and exposes them over HTTP/SSE per the official MCP spec (`mcp` Python SDK streamable HTTP transport, supported by `mcp>=1.0.0` already in `pyproject.toml`). Routes:
  - `POST /mcp/literature/*` → forwards to literature source server (via long-lived `MCPPool` instance)
  - `POST /mcp/lab/*` → forwards to lab source server
  - `POST /mcp/query` → calls `query/planner.py` for intent-routed federated query
- **Auth (CX16A)** — NO bearer middleware. Auth is enforced at the Cloudflare edge:
  - Dashboard hostname has Cloudflare Access policy (SSO/email magic link/IP allowlist for humans)
  - Gateway hostname has Cloudflare Access policy with **service tokens** allowed (machines)
  - FastAPI dependency validates the Cloudflare JWT in the `Cf-Access-Jwt-Assertion` header against Cloudflare's public keys; trusts `Cf-Access-Authenticated-User-Email` for humans and `Cf-Access-Service-Token-Name` for machines
- `src/llm_rag/config.py` — add `cf_access_team_domain: str`, `cf_access_aud_tag: str`, `cf_access_audience: str` settings, env-loaded.
- CORS middleware: allowlist from `Settings.gateway_cors_origins`.
- Long-lived `MCPPool` — single instance held by FastAPI app lifecycle, kept warm across requests.
- Wiki write serialization (CX12A): `src/llm_rag/wiki/writer.py` wraps every read-modify-write in `filelock.FileLock(path + ".lock")`. New dependency: `filelock>=3.0`.
- `src/llm_rag/cli.py` — `llm-rag serve --port 8443` to launch the gateway via uvicorn.
- `docker-compose.yml` (repo root) — bring up: source MCP servers (as stdio subprocesses spawned by gateway, not separate compose services — `MCPPool` owns their lifecycle), gateway, dashboard, Chroma. Use the existing dashboard image as the frontend.
- `cloudflared` config block in repo `deploy/cloudflared.example.yml` documenting the tunnel + ingress rules (separate hostname for dashboard vs gateway; both protected by Cloudflare Access policies).
- `.env.example` — document Cloudflare Access settings.

Tests:

- `tests/mcp/test_gateway_auth.py` — valid CF JWT → 200, missing header → 401, wrong AUD → 401, expired JWT → 401, malformed JWT → 401.
- `tests/mcp/test_gateway_cors.py` — allowlisted origin preflight → 200, disallowed origin → 403.
- `tests/mcp/test_gateway_query.py` — end-to-end query through gateway returns multi-source provenance citations.
- `tests/mcp/test_gateway_degraded.py` — kill source mid-query, assert response succeeds with warning naming the missing source.
- `tests/wiki/test_filelock.py` — two writers attempting concurrent writes serialize correctly; no partial writes.

### Step 5 — Reference writing-app integrations

Make the demo concrete and reproducible across all three target clients.

New files:

- `examples/writing-app/claude_desktop/claude_desktop_config.json` — copy-pasteable Claude Desktop MCP server config pointing at `https://<gateway-hostname>/mcp` with `CF-Access-Client-Id` + `CF-Access-Client-Secret` headers.
- `examples/writing-app/cursor/.cursor/mcp.json` — Cursor IDE MCP config snippet (same auth model).
- `examples/writing-app/python/client.py` — minimal Python script using `claude-code-sdk` (or `anthropic` SDK + MCP client lib) demonstrating: connect to gateway, query `/mcp/query` with a real reporting prompt, print drafted prose with provenance citations.
- `examples/writing-app/README.md` — setup instructions per client (Cloudflare service-token creation, env vars, hostname).
- `docs/api/v1.md` (CX-9) — full agent-facing API spec: stable request/response schema, citation payload format, streaming behavior, timeout semantics, error model, versioning policy, idempotency notes.

### Step 6 — Documentation updates

- `CLAUDE.md`: add a "MCP Gateway" section, document the new `serve` CLI command, add lab-doc page templates to Repository Layout, add `Sop`/`Meeting`/`InternalReport` to the Schema Types table, document the new doc_type enum, document the per-source auto-section naming convention for cross-source entities.
- `docs/roadmap.md`: mark V2 query intent + lab-doc ingest + external access as DONE; add V2.5 Neo4j threshold note; add federation-contract status (v0.1 published).

## 10. Test plan

This section consolidates the test coverage diagram from `/plan-eng-review` and the test-plan artifact written at `~/.gstack/projects/Ozzstein-Biblioteca/ozzstein-lab-knowledge-eng-review-test-plan-20260427-175538.md`.

### 10.1 Coverage diagram (plan-stage; all paths are GAPS until implementation)

```
CODE PATHS                                                  USER FLOWS / EVAL
[+] mcp/sources/literature.py (refactor)                    [+] F1: SOP ingest -> query
  ├── [REGRESSION CRITICAL] T1A snapshot catches drift        ├── [GAP] [E2E] Drop SOP, ingest, query
  └── [GAP] all tool functions                                ├── [GAP] SOP without frontmatter
                                                              └── [GAP] SOP with malformed YAML
[+] mcp/sources/lab.py (new)
  └── [GAP] all tool functions parallel to literature       [+] F2: Reporting via Claude Desktop
                                                              ├── [GAP] [E2E] python client end-to-end
[+] mcp/gateway.py (new)                                      └── [GAP] Multi-source provenance citations
  ├── CF JWT validation
  │   ├── [GAP] valid JWT -> 200                            [+] F3: Ambiguous query -> hybrid (A5A)
  │   ├── [GAP] missing header -> 401                         ├── [GAP] confidence < 0.7 -> hybrid
  │   ├── [GAP] wrong AUD -> 401                              ├── [GAP] boundary: confidence == 0.7
  │   ├── [GAP] expired JWT -> 401                            └── [GAP] classifier API fail -> hybrid
  │   └── [GAP] malformed JWT -> 401
  ├── CORS                                                  [+] F4: Source crash recovery (A3A)
  │   ├── [GAP] allowed origin preflight                      ├── [GAP] [E2E] Crash -> retry -> success
  │   ├── [GAP] disallowed origin -> 403                      ├── [GAP] Crash -> max retries -> unavailable
  │   └── [GAP] credentials handling                          └── [GAP] Degraded response names source
  └── route forwarding
      └── [GAP] all source routes succeed/fail correctly   [+] F5: SOP versioning (preserve old)
                                                              ├── [GAP] v2 over v1 -> linked entities
[+] mcp/pool.py (extended A3A)                                ├── [GAP] index.md current_version updated
  ├── spawn N from registry                                   ├── [GAP] Default returns current
  │   ├── [GAP] config parsing                                └── [GAP] --include-history returns both
  │   └── [GAP] missing required keys
  └── crash recovery with backoff                           [+] F6: Cross-source entity (A1B)
      ├── [GAP] crash -> retry 1s, 2s, 4s, 8s                 ├── [GAP] Both sources write evidence-{src}
      ├── [GAP] max retries -> mark unavailable               ├── [GAP] Reader merges both sections
      └── [GAP] subsequent restart on availability            └── [GAP] No section-name collision

[+] query/planner.py (new)                                  LLM EVAL-WORTHY (T2A)
  ├── intent classifier (Haiku)                               ├── [EVAL] extraction-paper (regression baseline)
  │   ├── [GAP] benchmark suite >=80% routing                 ├── [EVAL] extraction-sop (golden set)
  │   └── [GAP] confidence + intent both returned             ├── [EVAL] extraction-meeting (golden set)
  ├── confidence threshold (A5A)                              ├── [EVAL] extraction-report (golden set)
  │   ├── [GAP] conf < 0.7 -> hybrid                          ├── [EVAL] intent classifier (20-query)
  │   ├── [GAP] boundary == 0.7                               └── [EVAL] synthesis multi-source provenance
  │   └── [GAP] invalid intent -> hybrid
  └── route dispatch                                        FILELOCK (CX12A)
      ├── [GAP] reporting -> hybrid                           ├── [GAP] concurrent writers serialize
      ├── [GAP] know-how -> wiki + vector                     └── [GAP] no partial writes
      ├── [GAP] insight -> graph + vector
      └── [GAP] other -> hybrid                             AUTHORITY PRECEDENCE (CX-7)
                                                              └── [GAP] approved SOP wins over conflicting paper
[+] query/retrieval.py (4 routes)
  ├── [GAP] hybrid parallel fan-out                         FRESHNESS (CX13B)
  ├── [GAP] reranking merge                                   ├── [GAP] ingested_at on every entity
  └── [GAP] provenance preserved through merge                └── [GAP] verify-against-source UX in citations

[+] schemas/entities.py (new Sop/Meeting/InternalReport)    DOC_TYPE ENUM (C2A) - REGRESSION CRITICAL
  ├── [GAP] field defaults                                    ├── [GAP] each known alias maps correctly
  ├── [GAP] supersedes/superseded_by linkage                  ├── [GAP] unknown -> DocType.UNKNOWN
  └── [GAP] deprecated default                                └── [GAP] every existing manifest loads

[+] config/mcp-sources.yaml + tests/contracts/ (CX4A)
  ├── [GAP] schema validation
  ├── [GAP] MockSource passes conformance suite
  └── [GAP] capability negotiation

COVERAGE: 0/~60 paths tested at plan stage
REGRESSIONS (CRITICAL, IRON RULE): 2 — MCP refactor parity (T1A); doc_type enum existing manifest load
```

### 10.2 Eval suites required (T2A)

For each prompt below, JSONL golden set + pytest harness in `evals/`:

- `evals/extraction-paper.jsonl` — REGRESSION baseline (no behavior change expected)
- `evals/extraction-sop.jsonl` — golden set of 10–20 SOP examples → expected Sop entity fields
- `evals/extraction-meeting.jsonl` — golden set → expected Meeting entity
- `evals/extraction-report.jsonl` — golden set → expected InternalReport entity
- `evals/intent-classifier.jsonl` — 20-query benchmark, hand-labeled with intent + acceptable confidence range; assert ≥80% intent match
- `evals/synthesis-multisource.jsonl` — modified synthesis prompt, golden set with multi-source inputs → assertions on citation completeness (both source types cited when both present)

CI: eval suites run on PRs touching `agents/prompts/**`. Failure blocks merge.

### 10.3 Critical paths to verify end-to-end

- **F2 reporting**: Claude Desktop → CF Access service token → gateway → intent classifier → hybrid fan-out → literature + lab source servers → reranked merge → Sonnet synthesis → drafted prose with provenance citations. Must return citations to at least one internal source AND one literature source on a query that has data in both.
- **F4 source crash recovery**: kill source mid-flight, gateway must NOT 500. Either recovers (response succeeds with retry) or degrades gracefully (response succeeds with warning + missing source noted).
- **T1A refactor regression**: pre-refactor snapshot suite must replay byte-equivalent against post-refactor source servers.
- **C2A doc_type migration**: every existing `*.manifest.json` in the repo must load without Pydantic validation error after the enum change ships.

## 11. Failure modes per new codepath

| Codepath | Realistic failure | Test? | Error handling? | User-visible? |
|---|---|---|---|---|
| MCP source-server subprocess crash | OOM or chromadb segfault during query | A3A retries enforced via test | Backoff retry → mark unavailable | Yes — degraded response names missing source |
| Intent classifier wrong route | Borderline query gets single-route synthesis | A5A confidence-fallback test | Hybrid fan-out at conf<0.7 | No — answer just less complete (acceptable) |
| Cross-source wiki write race | literature + lab write same `material:lfp.md` simultaneously | filelock test required | filelock serializes (CX12A) | No — writes are sequential through lock |
| doc_type enum on existing manifest | Old free-form string fails Pydantic validation | C2A migration test (REGRESSION CRITICAL) | alias-map validator + UNKNOWN fallback | No |
| Refactor regression | New source-server tool returns different shape than monolithic predecessor | T1A snapshot test (REGRESSION CRITICAL) | None — caught at test time | Test would fail, blocking merge |
| Stale lab doc cited | SOP v5 in shared drive but v3 in corpus | Manual verification only at v1 | Citation surfaces `ingested_at` + `verify against source` (CX13B) | Yes — user sees date and warning |
| CF Access misconfig | Service token rejected by Cloudflare | Manual deploy verification | 401 returned by edge, never hits app | Yes — clear "auth failed" message |
| filelock deadlock | Long-held lock from crashed writer | Future TODO; v1 has reasonable lock timeout | `filelock` raises `Timeout`, gateway returns 503 | Yes — visible error |

**Critical gaps flagged: 0** — all known failure modes have either tests or visible error handling per the locked decisions.

## 12. Reused functions & utilities (what already exists)

- `src/llm_rag/mcp/pool.py:62-224` — `MCPPool` lifecycle, extended for spawn-N + restart-on-crash; not rewritten.
- `src/llm_rag/utils/chunking.py` — generic chunker, no changes.
- `src/llm_rag/schemas/entities.py:57-75` — existing `Material`/`Cell`/`Claim` pattern, copy for new lab entities.
- `src/llm_rag/wiki/{reader.py, writer.py}` — section-fence parser/writer. Extend with per-source-suffix support (A1B) + `filelock` wrap (CX12A). Section-fence rule from `CLAUDE.md` is invariant.
- Existing `IngestionAgent`, `ExtractionAgent`, `NormalizationAgent`, `WikiCompilerAgent`, `GraphCuratorAgent` — unchanged behavior, only routed by doc_type.
- Existing `QueryAgent` — becomes a synthesis backend used by the new planner.
- Existing dashboard FastAPI app (`web/api/main.py`, 549 lines) — unchanged routes; only addition is the Cloudflare JWT validation dependency replacing the localhost-CORS posture.
- `mcp>=1.0.0`, `fastapi>=0.109.0`, `uvicorn[standard]>=0.27.0`, `python-frontmatter`, `pydantic>=2`, `chromadb>=0.5.0`, `networkx[default]>=3.3` — already in `pyproject.toml`.
- `langgraph` is NOT in deps — query planner uses stdlib state machine, not LangGraph.
- `config/entity-normalization.yaml` — already exists; CX-6 extends it with internal-alias categories.
- Existing 38 tests — must pass unchanged after Step 1 (T1A snapshot enforces this).

**Only new dependency:** `filelock>=3.0`.

## 13. Worktree parallelization strategy

Module-level dependency table:

| Step | Modules touched | Depends on |
|------|----------------|------------|
| Step 0 | `CLAUDE.md` only | — |
| Step 0a | (no code; manual user labeling) | — |
| Step 1 | `src/llm_rag/mcp/`, `tests/contracts/`, `tests/snapshots/`, `docs/` | Step 0 |
| Step 2 | `src/llm_rag/schemas/`, `src/llm_rag/pipeline/`, `agents/prompts/`, `config/page-templates/`, `config/entity-normalization.yaml`, `src/llm_rag/mcp/sources/lab.py`, `src/llm_rag/wiki/` | Step 1 |
| Step 3 | `src/llm_rag/query/`, `agents/prompts/intent-classifier.md` | Step 0a (for evals) |
| Step 4 | `src/llm_rag/mcp/gateway.py`, `src/llm_rag/mcp/pool.py`, `src/llm_rag/config.py`, `docker-compose.yml` | Steps 1, 2, 3 |
| Step 5 | `examples/writing-app/`, `docs/api/v1.md` | Step 4 |
| Step 6 | `CLAUDE.md`, `docs/roadmap.md` | Step 5 |

Lanes:

```
Lane A (sequential, blocking):     Step 0 -> Step 1 -> Step 4 -> Step 5 -> Step 6
Lane B (parallel after Step 1):    Step 2 (lab-doc ingest, schemas, prompts, config)
Lane C (parallel from Step 0):     Step 3 (query/, intent-classifier prompt)
Lane D (parallel from start):      Step 0a (manual corpus curation, no code conflict)
```

Conflict flags:
- Lane A's Step 4 touches `src/llm_rag/mcp/pool.py`; Lane A's Step 1 also touches it. Sequential within Lane A — safe.
- Lane B (Step 2) and Lane C (Step 3) both touch `agents/prompts/` — different files (`extraction-*.md` vs `intent-classifier.md`). Safe in parallel.
- Lane B and Lane C don't touch each other's primary modules. Genuinely parallel.

Execution order: Step 0 alone → launch Step 1 → on Step 1 merge: launch Step 2 + Step 3 in parallel worktrees, plus Step 0a (manual) in background → on both merge: Step 4 → Step 5 → Step 6.

## 14. Verification

End-to-end test plan, in order:

1. **Step 0:** `git checkout -b Ozzstein/lab-knowledge && git status` clean. CLAUDE.md has skill-routing block. `git log -1` shows the chore commit.
2. **Step 1:** `uv run pytest tests/snapshots/ tests/contracts/ tests/mcp/test_pool_*.py -v` — snapshot replay green; conformance suite green; pool spawn-N + restart green. Existing 38 tests green.
3. **Step 2:** Drop a real SOP markdown into `raw/sop/`; run `uv run llm-rag ingest --doc-id sop/<id>`; verify `wiki/sop/<id>/v1.md` and `index.md` are created from the new template. `uv run llm-rag ask "what is our SOP for X"` finds it. Cross-source test: ingest a paper that mentions an internal material; both literature and lab evidence-* sections appear in `wiki/materials/<material>.md`.
4. **Step 3:** `uv run pytest tests/query/ -v` — classifier ≥80% on the 20-query benchmark; confidence-threshold and authority-precedence tests pass. Manual spot-check of 5 queries via `uv run llm-rag ask "..." --mode auto` routes correctly.
5. **Step 4:** `uv run llm-rag serve --port 8443` starts the gateway. `cloudflared tunnel run` exposes it. From a separate machine: `curl -H "CF-Access-Client-Id: ..." -H "CF-Access-Client-Secret: ..." https://<gateway-hostname>/mcp/query -d '{"query":"..."}'` returns provenance-tagged result. Same call without service-token headers: 401 from Cloudflare. `docker-compose up` brings up the full stack on the host.
6. **Step 5:** Configure Claude Desktop with `claude_desktop_config.json` + service-token env vars. Ask "draft a 3-page summary of LFP cathode degradation including our internal SOPs and reports" — Claude Desktop calls the gateway, gets back drafted prose with citations to both internal and published sources. Run `python examples/writing-app/python/client.py` and verify the same. Repeat with Cursor.
7. **Step 6:** `uv run mypy src/` — clean. `uv run ruff check src/ tests/` — clean. `uv run pytest tests/ -v` — all green. `uv run pytest evals/ -v` — all eval suites pass thresholds. Roadmap reflects V2 done, V2.5 documented.

## 15. Review record

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Office Hours | `/office-hours` | Problem framing & wedge selection | 1 | DONE | Reporting selected as wedge; Approach B chosen; 6 open questions resolved |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 13 explicit decisions locked; 0 critical gaps; 0 unresolved |
| Outside Voice | `codex` (read-only, high reasoning) | Independent challenge | 1 | issues_found → resolved | 20 challenges; 6 → cross-model decisions, 7 → folds, 2 → known risks, 5 → absorbed |
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | not run | Settled in /office-hours; no business pivot since |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | not run | Optional — only Step 5 reference clients have a UX surface |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | not run | — |

**VERDICT:** ENG CLEARED — ready to implement.

**Cross-model:** Claude review and Codex outside voice converged on most architectural concerns. Diverged on (a) MCP federation as the right abstraction (Codex skeptical) and (b) plan size (Codex wanted smaller — user explicitly chose Approach B). Both divergences resolved by user decision; the federation-contract amendment (CX4A) addresses Codex's most concrete operational concern.

**UNRESOLVED:** 0.

## 16. Historical artifacts

These are the per-tool artifacts that produced the content in this consolidated file. They remain for traceability; **this file is the canonical reference.**

- Office-hours design doc: `~/.gstack/projects/Ozzstein-Biblioteca/ozzstein-lab-knowledge-design-20260427-155918.md`
- Eng-review plan file: `~/.claude/plans/replicated-soaring-teacup.md`
- Eng-review test plan (consumed by `/qa`): `~/.gstack/projects/Ozzstein-Biblioteca/ozzstein-lab-knowledge-eng-review-test-plan-20260427-175538.md`
