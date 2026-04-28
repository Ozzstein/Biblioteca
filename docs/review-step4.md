# Step 4 Eng Review — `9a72d5b feat(step4): add MCP-over-HTTP gateway`

**Reviewer:** CTO-mode workspace, against `origin/Ozzstein/lab-knowledge` @ `9a72d5b`.
**Date:** 2026-04-28.
**Verdict:** **APPROVED with 4 minor follow-ups.** Safe to merge to `main` once follow-ups land or are explicitly deferred to Step 5.

This was a tight, contract-faithful Step 4. Auth, filelock, restart-aware degraded responses, CORS, lifespan management, and tests are all done correctly. No re-architecture needed.

---

## Verification (run from this CTO workspace, ephemerally)

| Check | Result |
|---|---|
| Full test suite | **735 passing**, 1 skipped (was 723 after Step 3; +12 net from gateway + filelock tests) |
| `tests/mcp/test_gateway_*.py` + `tests/wiki/test_filelock.py` | All 12 green |
| ruff on Step 4 files | clean |
| New deps added correctly | `pyjwt[crypto]>=2.12.1`, `filelock>=3.0` (also: `fastapi>=0.136.1`, `uvicorn[standard]>=0.44.0` bumped) |
| Existing T1A snapshot suite | still byte-equivalent |

---

## What was done well

1. **CX16A compliance is perfect.** No bearer middleware anywhere. CF Access JWT is the sole auth path on both gateway (`src/llm_rag/mcp/gateway.py:161`) AND existing dashboard (`web/api/main.py:35`). The handoff brief's most important constraint was honored exactly.
2. **JWT validation is implemented correctly.** `src/llm_rag/auth/cloudflare.py`:
   - Verifies signature against JWKS (RS256, ES256) — line 126
   - Validates `aud` claim against `cf_access_aud_tag` — line 127
   - Requires `exp` and `aud` claims explicitly — line 128
   - Selects key by `kid` from JWT header (correct multi-key support) — lines 87-92
   - Caches JWKS for 1h (`_JWKS_CACHE_TTL_SECONDS = 3600`) — avoids hammering Cloudflare
   - Returns 401 on every failure mode (missing, malformed, expired, wrong AUD); returns 503 if CF settings are missing entirely (correctly distinguishes config error from auth error)
3. **CX12A filelock done right.** `wiki/writer.py` wraps both `update_auto_sections` and `create_page` in `FileLock(path + ".lock", timeout=10)`. The concurrent-writer test (`tests/wiki/test_filelock.py:24`) actually races two `ThreadPoolExecutor` workers and asserts no lost updates — real concurrency, not theatre.
4. **A1B per-source naming with backward compat.** `_resolve_section_name` in `wiki/writer.py:12` maps `evidence` → `evidence-literature` for the default source AND falls back to legacy un-suffixed sections if the suffixed pair isn't present. Smart — won't break wiki pages from before Step 2.
5. **A3A degraded responses.** `SourceUnavailable` is caught at the gateway (`gateway.py:185`) and returns `{degraded: true, missing_source, result: null}` with HTTP 200, NOT 500. This is exactly what the handoff brief's §4.3 specified.
6. **Filelock timeout → 503.** Mapped at the gateway layer (`gateway.py:187-188, 223-224`), not at the writer. Writer raises `filelock.Timeout`; gateway translates to HTTPException(503). Clean separation.
7. **Tests are real, not mock-of-mocks.** `tests/mcp/test_gateway_auth.py` generates actual RSA keys, signs real JWTs with `pyjwt`, only mocks the JWKS HTTP fetch. FastAPI `TestClient` exercises the dependency chain end-to-end.
8. **CORS is custom middleware (not FastAPI's `CORSMiddleware`)** — and correctly handles preflight (200 + ACA-Origin + ACA-Headers + ACA-Methods), enforces allowlist (`gateway_cors_origins` from settings), and supports `*` wildcard. Disallowed origin → 403 on preflight.
9. **`docs/api/v1.md` shipped** (this was technically Step 5's CX-9 deliverable; Step 4 agent did it as a courtesy). Step 5 will need to expand it — see follow-up #1 below.
10. **`/mcp/health` and `/mcp/sources`** added per the handoff brief — useful for the Python client's pre-flight sanity check.
11. **Lifespan management correct.** Single long-lived `MCPPool` held by `app.state.pool`, constructed via `_default_pool_factory` → `MCPPool.from_yaml(...)`. Planner constructed once and reused. `pool_factory` is injected so tests can swap in `FakePool`.

---

## Follow-ups (4)

These are NOT blockers; they can be addressed in Step 5 or a subsequent cleanup commit. Listed in priority order.

### F1 — `docs/api/v1.md` is thin (~100 lines); Step 5 must expand it

The shipped spec covers auth, the 5 routes, and the basic JSON shapes — but the handoff brief §5.4 lists much more that the sister project will need:

- **Citation payload format** — the spec shows `"citations": []` but never defines what's in a citation object. Sister project will need: source name, doc_id, chunk index/page, confidence, ingested_at (CX13B), verify-against-source flag.
- **Streaming behavior** — not documented. Currently whole-result; if you intend to add SSE later, say "v1.x future."
- **Timeout semantics** — only filelock 503 is mentioned; nothing about source subprocess timeout.
- **Idempotency** — not addressed.
- **Versioning policy** — no semver statement, no compatibility window.
- **Error model** — only auth errors documented. Need a comprehensive 4xx/5xx table.
- **Out-of-scope notes** — explicit "what's NOT in v1" so external consumers don't ask.
- **Allowed query modes** — line 99 says `wiki|vector|graph|hybrid|auto` but the user-job intents from CX-3 (`reporting|know-how|insight|other`) live inside the planner. The spec should clarify the user-facing names vs the internal route names.

**Action:** Step 5 agent expands `docs/api/v1.md` per the handoff brief §5.4. **Don't merge as-is to main if you treat the API spec as a hard contract for sister-project integration**; merge the Step 5 expansion first.

### F2 — Dashboard CORS still hardcodes localhost (`web/api/main.py:41`)

The CF Access dependency was added to the dashboard FastAPI app, but `CORSMiddleware` still hardcodes `["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]`. Once the dashboard is reachable through Cloudflare Tunnel, browsers loading from the public hostname will fail CORS.

**Action:** Replace the hardcoded list with `Settings.gateway_cors_origins` (or add a separate `dashboard_cors_origins` field). One-line change. Either commit-back to `Ozzstein/lab-knowledge` or fold into Step 5 / Step 6.

### F3 — Dashboard `/api/query` still uses `QueryAgent`, not `QueryPlanner`

`web/api/main.py:515` imports `QueryAgent` instead of the new `QueryPlanner` from Step 3. Result: human dashboard users get the old single-path retrieval; the new intent classification + hybrid fallback is gateway-only.

This may be intentional (dashboard is for humans browsing, not for agentic queries) but it's not documented and creates a drift between dashboard and gateway behavior.

**Action:** Either explicitly note in CLAUDE.md that the dashboard `/api/query` is a "lite" endpoint without intent classification, OR update it to use `QueryPlanner` like the gateway does. Lean toward updating — DRY. Defer to Step 6 if scope-tight.

### F4 — `_default_pool_factory` hardcodes a relative path (`gateway.py:29`)

`MCPPool.from_yaml("config/mcp-sources.yaml", ...)` only works if uvicorn is started with the repo root as cwd. Fine for `docker-compose up`; brittle for ad-hoc dev/prod runs.

**Action:** Use `PROJECT_ROOT / "config" / "mcp-sources.yaml"` from `llm_rag.config`, OR add a Settings field `mcp_sources_yaml_path`. Two-line change.

---

## Notes — NOT follow-ups, just observations

- **CORS on success responses also sets ACA-Origin** (`gateway.py:141-142`) — middleware adds CORS headers to every non-preflight response when origin is in the allowlist. There's no test verifying this on a 200 success response (only the preflight 200 is tested), but the implementation is correct.
- **`_query_citations` accesses `result.context_bundle.citations`** (`gateway.py:72`) — implicit coupling to `QueryPlanner.ask`'s return shape. Acceptable since both are owned in this repo, but if the planner changes its return type a runtime AttributeError will pop up. Belt-and-suspenders: `getattr(result, 'context_bundle', None)`. Skip unless you want defensive code.
- **The `dependencies=[Depends(require_cloudflare_access)]` on `create_app`** applies the CF Access check to ALL routes including `/mcp/health`. This is the right call — the JWKS endpoint and source registry are not public information.
- **Test coverage is good but light on the `/mcp/sources`, `/mcp/health`, and `/mcp/lab/*` routes specifically.** They're exercised indirectly via `/mcp/literature/*` and `/mcp/health` in the auth tests, but no dedicated test asserts e.g. that `/mcp/sources` redacts subprocess commands. Acceptable for v1 — gateway isn't exposing the commands by design (only `name` + `capabilities` per `_source_registry`).

---

## Step 5 prep — already partially done by Step 4

Step 4 agent shipped `docs/api/v1.md` (which was Step 5's CX-9 deliverable). When Step 5 starts, that agent should:

1. **Don't redo the API spec from scratch — extend the existing one** per F1 above.
2. **Build the three reference clients** (Claude Desktop, Cursor, Python) per `docs/handoff-step5.md` §5.1–5.3.
3. **Address F2-F4 as part of Step 5 or note them as separate cleanups.**

I'll update `docs/handoff-step5.md` to point at this review's F1 specifically.

---

## Verdict

**APPROVED.** The implementation is faithful to the handoff brief and the canonical plan's locked decisions. The 4 follow-ups are minor (one is a real CORS bug, three are polish/spec-expansion). None block merging to `main`, but F1 (API spec expansion) should land before any external integrator (sister project) starts building against `docs/api/v1.md`.

Recommended commit-graph integration:

1. Merge `Ozzstein/lab-knowledge` → `main` now (or after Step 5).
2. Step 5 ships F1 (expanded spec) + reference clients + ideally F2-F4 cleanups.
3. Step 6 doc updates close the loop on CLAUDE.md, roadmap.md.
