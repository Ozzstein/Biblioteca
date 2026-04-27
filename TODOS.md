# TODOs

Captured from `/plan-eng-review` of the lab-knowledge extension design on 2026-04-27. None are blocking the v1 ship of that plan; all are valuable post-v1 work.

---

## TODO-1: Shared-drive filesystem-watch connector for lab docs

**What:** Add `src/llm_rag/research/subagents/filesystem.py` watcher monitoring a configurable shared-drive mount (NFS / SMB / Google Drive File Stream) and queueing changed files for re-ingest, with tombstones on deletes.

**Why:** The v1 plan ships freshness *visibility* (citations carry `ingested_at`, `source_url`) via decision CX13B but doesn't *fix* freshness. For audit / compliance contexts a real sync layer is eventually needed.

**Pros:**
- Eliminates manual drop step
- Always-fresh wiki / graph
- Closes one of the most piercing critiques from the eng review (Codex #13)

**Cons:**
- ~1 week of work
- Only covers mountable drives (SharePoint Online needs a separate API connector)
- Deletion semantics need careful design — when does a deleted SOP become superseded vs hard-removed?

**Context:** `CX13C` was rejected during review in favor of the lighter `CX13B` (freshness metadata). Worth revisiting once the lab corpus is real and managers experience the staleness pain firsthand.

**Depends on:** Step 2 (lab-doc ingest) shipped + real lab corpus in `raw/sop/` for at least 1 month.

---

## TODO-2: End-to-end report-task eval suite

**What:** A pytest-runnable suite under `evals/end-to-end/` where each fixture is a "draft a report on topic X" task. Assertions: drafted report cites N+ internal sources, M+ external sources, mentions K specific entities expected from the corpus, completes within T tokens. Measures actual reporting value, not just per-prompt accuracy.

**Why:** Codex critique #14 — the per-prompt evals (`T2A`) validate components, not the workflow. Reporting is the chosen wedge; an eval that measures reporting itself is the only real signal the system is doing its job.

**Pros:**
- Captures reporting regressions before users notice
- Gives a concrete time-to-draft-report metric to track over time
- Closes the eval-misalignment critique

**Cons:**
- Labor-intensive — manager has to write the "ideal" output for each task
- Golden reports decay as corpus changes

**Context:** `T2A` locked the per-prompt eval framework. This is the layer above. Worth doing once the system actually drafts real reports end-to-end (after Step 5) so there's a baseline to measure against.

**Depends on:** Step 5 shipped + CX14/15 corpus curation done.

---

## TODO-3: LRU query result cache in the gateway

**What:** Add LRU cache (`functools.lru_cache` or `cachetools`) on `(query_text, mode, source_set_hash) → response` in the gateway. Configurable size and TTL.

**Why:** Identical queries replay the full pipeline (intent classification + retrieval + synthesis). For a repeat-report workflow (managers often re-run the same monthly query), this cuts latency and token spend.

**Pros:**
- Trivial (~5–10 lines of code)
- Large user-perceived speedup on repeat queries
- Reduces token spend on cache hits

**Cons:**
- Stale results when corpus updates — need cache invalidation on ingest completion or short TTL
- Cache key must be canonicalized (whitespace, case) to actually hit

**Context:** Performance issue P3 from the eng review — flagged, not chosen as current-PR. Low effort, high payoff once usage settles into patterns.

**Depends on:** Step 4 (gateway) shipped.
