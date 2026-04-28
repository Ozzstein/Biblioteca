# Step 5 Eng Review — PR #6 `Ozzstein/lab-knowledge-step5`

**Reviewer:** CTO-mode workspace, against `origin/Ozzstein/lab-knowledge-step5` (3 commits: `ecf3c98`, `ce0dd25`, `8c43acd`).
**Date:** 2026-04-28.
**Verdict:** **APPROVED with 3 minor concerns.** Safe to merge to `main`.

The agent overdelivered on this PR — handled all four follow-ups from the Step 4 review (F1–F4), produced the three reference clients per the brief, **and** added the actual MCP-over-HTTP protocol bridge that was implicit in the handoff brief but not yet wired up. That last addition was the right call: without it, Claude Desktop and Cursor cannot reach the gateway over their MCP transports, and the demo doesn't actually work.

---

## Verification

I cannot run the test suite from this CTO branch (it predates the Step 4 merge), but reviewed the diff in detail. The PR adds:

- **+290 / -31** in `docs/api/v1.md` (327 total)
- **+188 / -68** in `src/llm_rag/mcp/gateway.py` (364 total)
- **+82 / -68** in `web/api/main.py`
- **3 new test files** (`test_gateway_mcp_protocol.py` 114 lines, `test_python_client_smoke.py` 88 lines, `test_api_spec_examples_parse.py` 14 lines)
- **8 reference-client files** under `examples/writing-app/`

Trust signal: the agent reported "Step 5 is finished," and the PR is in OPEN state. Recommend the implementing workspace runs `uv run pytest tests/ && uv run ruff check src/ tests/` and posts the result on the PR before merge.

---

## What was done well

### F1 — API spec expansion (the most important deliverable)

The expanded `docs/api/v1.md` (327 lines, was 99) addresses every gap I called out in the Step 4 review:

- **Versioning Policy** — semver, breaking changes require `v2.md`, deprecated v1 fields keep working through one minor after v2 ships.
- **Error Model** — full table mapping HTTP status to `error.code` (e.g., `401 unauthorized`, `408 source_timeout`, `503 wiki_lock_timeout`, `503 all_sources_unavailable`, `500 internal_error` with `request_id` for correlation). Better than asked: keys behavior off both status code AND `error.code`.
- **Citation Payload Format** — concrete shape with all fields documented (`source`, `doc_id`, `chunk_index`, `page`, `quote`, `confidence`, `ingested_at`, `verify_against_source`, `citation_type`). v1 clients told to accept missing optional fields.
- **Idempotency** — per-endpoint notes. Read tools safe to retry; write tools not replay-protected in v1.0.0; clients own their own keys.
- **Streaming Behavior** — explicit "v1.0.0 returns whole JSON; future v1.x may add SSE" with sample event sequence.
- **Timeout Semantics** — wiki lock 10s → 503; reverse-proxy timeouts deferred to deployment; future v1.x may add app-level timeout returning `408 source_timeout`.
- **Out Of Scope For v1** — explicit list (multi-tenant, bearer fallback, report templates, pagination, SDK generation, streaming).

Sister project can integrate against this without asking questions.

### F2 — Dashboard CORS

`web/api/main.py:_dashboard_cors_origins()` now reads `Settings.gateway_cors_origins` with the localhost dev-fallback. Real bug fixed.

### F3 — Dashboard `/api/query`

Replaced the `QueryAgent` import with `QueryPlanner` + `MCPPool.from_yaml(...)`. Returns `intent`/`confidence`/`route`/`sources` in the response `context`. Behavior parity with the gateway's `/mcp/query`.

### F4 — Gateway config path

`_default_pool_factory` now uses `PROJECT_ROOT / "config" / "mcp-sources.yaml"` instead of the brittle relative `"config/mcp-sources.yaml"`. Brittle path eliminated.

### Reference clients (the brief's main deliverable)

- **Python client** (`examples/writing-app/python/client.py`) — 81 lines, uses `mcp.client.streamable_http.streamablehttp_client`, reads env vars via `python-dotenv`, factories injected for testability. The smoke test (`test_python_client_smoke.py`) actually exercises the real connect-init-call-tool flow with mocked transport. Real test, not theatre.
- **Cursor config** — uses the standard `mcpServers` shape with `${CF_ACCESS_*}` placeholders. Correct.
- **Claude Desktop config** — see C2 below for one concern.
- **Both READMEs** ship setup steps.

### Unexpected scope add — actual MCP-over-HTTP protocol bridge

This was the right call:

- `_mcp_protocol_app(runtime)` constructs a `FastMCP("biblioteca-gateway", streamable_http_path="/mcp", json_response=True, stateless_http=True)` instance and registers a single `query` tool that proxies to the same `_query_payload` function used by the REST `/mcp/query` route. Same shape, two transports.
- `_install_mcp_protocol_route` mounts the FastMCP app's streamable HTTP route into the parent FastAPI app, **wrapping it in `CloudflareAccessASGI`** — a custom ASGI middleware that runs `require_cloudflare_access` before forwarding. Necessary because the FastMCP app is mounted as a starlette `Route` and doesn't go through FastAPI's dependency injection.
- `CloudflareAccessASGI` reuses `app.dependency_overrides` for testability — clean.
- New test `test_gateway_mcp_protocol.py` exercises the route end-to-end via JSON-RPC 2.0 over HTTP (the actual MCP wire format).

Without this, Claude Desktop and Cursor would have nothing to connect to (their MCP clients speak HTTP/SSE per the spec, not arbitrary REST). The handoff brief implied it (§4.3 said "wraps the source MCP servers and exposes them over HTTP/SSE per the official MCP spec"); Step 4 didn't actually wire up FastMCP, only REST. Step 5 closed the gap.

---

## Concerns (3, none blocking)

### C1 — Citation `source` field derived by string-prefix matching

`gateway.py:_query_citations` line:
```python
source = "lab" if doc_id.startswith(("sop/", "meeting/", "report/")) else "literature"
```

This works for the current convention but is fragile. A literature paper that happened to have doc_id `"report/foo"` (e.g., a published technical report) would be misclassified as lab. Better: track which source server actually returned the citation (from `pool.get(name).call_tool(...)`) and propagate that through `QueryResult` / `QueryContextBundle`. Tracked debt.

**Action:** Note in `docs/api/v1.md` that the `source` field is best-effort in v1.0.0 and may be inferred from `doc_id`. Plan a v1.1 fix where the source is propagated through the planner.

### C2 — Claude Desktop config uses `enterpriseConfig.managedMcpServers` (MDM format)

The config shape is:
```json
{
  "enterpriseConfig": {
    "managedMcpServers": "[{\"name\":...,\"transport\":\"http\",...}]"
  }
}
```

This is the **enterprise/MDM-managed** format — it works only when Claude Desktop is configured by an admin via MDM (e.g., a managed `.plist` on macOS), not when a user drops the file into `~/Library/Application Support/Claude/claude_desktop_config.json`. The standard per-user config uses `mcpServers` directly (the same shape Cursor uses).

If the target audience is the user's lab IT department deploying Claude Desktop via MDM, this is correct. If it's a bench scientist who wants to enable the gateway personally, the README needs a second config snippet OR this needs to switch to `mcpServers`.

**Action:** Either (a) verify with the org which deployment model applies and adjust, or (b) ship both configs in the README labeled "Personal user" vs "MDM-managed."

### C3 — Dashboard `/api/query` opens a fresh `MCPPool` per request

```python
async with MCPPool.from_yaml(registry_path) as pool:
    result = await planner.ask(...)
```

Each `MCPPool.__aenter__` spawns the literature + lab subprocesses, waits for their MCP handshake, runs the query, then tears down. That's roughly **seconds** of cold-start latency per dashboard query. The gateway uses a long-lived pool via FastAPI's lifespan context; the dashboard should do the same.

This may be intentional — the dashboard is rarely queried, agentic clients should use `/mcp/query`. But the perf hit will be visible to humans browsing.

**Action:** Either (a) move the dashboard's MCPPool to a lifespan-managed singleton like the gateway, or (b) document explicitly in CLAUDE.md that `/api/query` is a slow human-fallback and `/mcp/query` is the production path. Lean toward (a) — DRY with the gateway.

---

## Verdict

**APPROVED.** All four follow-ups from the Step 4 review are addressed. The bonus MCP protocol bridge is the right addition and unblocks the actual Claude Desktop / Cursor integration. The three concerns are real but minor — none block merging.

Recommended merge plan:

1. The Step 5 workspace pushes `uv run pytest tests/` + `uv run ruff check` results onto the PR (or you confirm green locally on the Step 5 worktree).
2. Merge PR #6 → `main`.
3. C1 (citation source propagation) goes to TODOS.md as a v1.1 follow-up.
4. C2 (Claude Desktop MDM vs personal config) — confirm which the org needs and patch in a follow-up commit.
5. C3 (dashboard MCPPool lifespan) — fold into V2 Step 6 documentation pass, or make it the first change after merge.
