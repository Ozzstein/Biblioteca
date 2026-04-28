# Handoff: Step 4 — MCP-over-HTTP Gateway

**Branch:** `Ozzstein/lab-knowledge` (current HEAD: `392b419`)
**Authoritative plan:** `docs/superpowers/plans/2026-04-27-v2-lab-knowledge-extension.md` §9 Step 4
**Status of prerequisites:** Steps 1, 2, 3 all committed + pushed. 723 tests passing.

You own Step 4. This note tells you what's already done, what to build, and the exact integration points so you don't re-read three plan files.

---

## What you're building (one-paragraph version)

A FastAPI gateway at `src/llm_rag/mcp/gateway.py` that:
1. Authenticates inbound requests via Cloudflare Access JWT (no bearer middleware — see CX16A below).
2. Holds a long-lived `MCPPool.from_yaml("config/mcp-sources.yaml")` warm across requests.
3. Forwards `/mcp/literature/*` and `/mcp/lab/*` to the corresponding source-server subprocesses.
4. Exposes `/mcp/query` that calls `QueryPlanner` for intent-routed federated queries with multi-source provenance.
5. Wraps every wiki-page write in a `filelock.FileLock` (new dep) to serialize concurrent writes from the literature + lab source-server subprocesses.

Plus reference clients in `examples/writing-app/` (Step 5) and an API spec in `docs/api/v1.md` (CX-9).

---

## What's already done (do NOT reimplement)

| Capability | Where | Status |
|---|---|---|
| MCP source-server registry from YAML | `src/llm_rag/mcp/pool.py:load_servers_from_yaml()` | ✅ |
| `MCPPool.from_yaml(path)` constructor | `src/llm_rag/mcp/pool.py:MCPPool.from_yaml` | ✅ |
| Restart-on-crash with exponential backoff (A3A, 1s/2s/4s/8s/16s, max 5) | `src/llm_rag/mcp/pool.py:_run_server` | ✅ |
| `SourceUnavailable` exception (subclass of `KeyError`) for degraded responses | `src/llm_rag/mcp/pool.py:SourceUnavailable` | ✅ |
| `pool.unavailable: dict[str, str]` for naming missing sources in warnings | `src/llm_rag/mcp/pool.py:MCPPool.unavailable` | ✅ |
| `literature` MCP source server (aggregator over corpus_io+wiki_io+graph_io) | `src/llm_rag/mcp/sources/literature.py` | ✅ |
| `lab` MCP source server (Sop/Meeting/InternalReport) | `src/llm_rag/mcp/sources/lab.py` | ✅ |
| Federation contract v0.1 spec | `docs/mcp-source-protocol-v0.1.md` | ✅ |
| Conformance suite (mock + lab + literature pass) | `tests/contracts/test_source_conformance.py` | ✅ |
| `MockSource` reference impl | `src/llm_rag/mcp/sources/mock.py` | ✅ |
| Source registry with both sources + their capabilities | `config/mcp-sources.yaml` | ✅ |
| `QueryPlanner` (intent classifier + 4 routes + A5A confidence-threshold hybrid fallback + CX-7 authority precedence) | `src/llm_rag/query/planner.py` | ✅ |
| `--mode {wiki,vector,graph,hybrid,auto}` CLI flag | `src/llm_rag/cli.py:ask` | ✅ |
| Per-source auto-section wiki convention (A1B) | `src/llm_rag/wiki/{reader,writer}.py` | ✅ |
| SOP versioning layout (`wiki/sop/<id>/v<n>.md` + `index.md`) | `src/llm_rag/wiki/{reader,writer}.py` | ✅ |
| Pre/post-refactor T1A snapshot suite (regression net) | `tests/snapshots/test_mcp_snapshots.py` | ✅ |
| `Sop` / `Meeting` / `InternalReport` Entity subclasses with status + version + ingested_at + source_url | `src/llm_rag/schemas/entities.py` | ✅ |
| `DocType` enum + alias-map field validator | `src/llm_rag/schemas/provenance.py` | ✅ |

---

## What you build

### 4.1 Settings additions

`src/llm_rag/config.py` — add three env-loaded settings:

```python
cf_access_team_domain: str = Field(default="", alias="CF_ACCESS_TEAM_DOMAIN")  # e.g. yourorg.cloudflareaccess.com
cf_access_aud_tag: str = Field(default="", alias="CF_ACCESS_AUD_TAG")          # the AUD claim from the CF Access app
gateway_cors_origins: list[str] = Field(default_factory=list, alias="GATEWAY_CORS_ORIGINS")
```

No `MCP_BEARER_TOKEN` — bearer middleware was explicitly dropped per CX16A.

### 4.2 Cloudflare Access JWT validation

FastAPI dependency that:
1. Reads `Cf-Access-Jwt-Assertion` header.
2. Fetches the JWKS from `https://<cf_access_team_domain>/cdn-cgi/access/certs` (cache for at least 1h).
3. Verifies signature, expiration, and `aud` claim matches `cf_access_aud_tag`.
4. Returns the principal: either `Cf-Access-Authenticated-User-Email` (humans on the dashboard hostname) or `Cf-Access-Service-Token-Name` (writing-app machines).
5. Raises `HTTPException(401)` on missing / invalid / expired JWT.

Use `PyJWT[crypto]` (add to `pyproject.toml`). Don't roll your own JWT verification.

The dashboard FastAPI app (`web/api/main.py`) gets the same dependency so its existing routes also become CF-Access-protected (per the auth pivot — A2C is superseded by CX16A, see canonical plan §7.5).

### 4.3 Gateway routes

```
POST /mcp/literature/{tool_name}        → forward to literature source via MCPPool
POST /mcp/lab/{tool_name}               → forward to lab source via MCPPool
POST /mcp/query                         → call QueryPlanner.ask(...)
GET  /mcp/health                        → returns {sources: [...], unavailable: {...}}
GET  /mcp/sources                       → returns the registry (names + capabilities, no commands)
```

Forward via `pool.get(name).call_tool(tool_name, params)`. On `SourceUnavailable`, return 200 with `{"degraded": true, "missing_source": "<name>", "result": <fallback>}`.

`/mcp/query` returns:
```json
{
  "answer": "...",
  "intent": "reporting",
  "confidence": 0.92,
  "route": "hybrid",
  "citations": [...],
  "sources_consulted": ["literature", "lab"],
  "sources_unavailable": []
}
```

### 4.4 Filelock around wiki writes (CX12A)

Add `filelock>=3.0` to `pyproject.toml`. Wrap every wiki page read-modify-write in:

```python
from filelock import FileLock
with FileLock(str(path) + ".lock", timeout=10):
    # existing read-modify-write
```

Touch points: `src/llm_rag/wiki/writer.py` `update_auto_sections`, `create_page`, and any other write helper. On `filelock.Timeout`, raise an HTTPException(503) at the gateway layer (not at the writer, which should propagate the exception).

### 4.5 Long-lived MCPPool

Single instance owned by FastAPI's lifespan context manager. Construct via:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = MCPPool.from_yaml("config/mcp-sources.yaml", max_restarts=5)
    async with pool:
        app.state.pool = pool
        yield
```

### 4.6 CLI launcher

```
llm-rag serve --port 8443 --host 127.0.0.1
```

Add a `serve` command in `src/llm_rag/cli.py` that calls `uvicorn.run(...)` against the gateway app.

### 4.7 docker-compose.yml

Repo root. Bring up: gateway (uvicorn), dashboard (existing), Chroma (existing). Source-server subprocesses are spawned by the gateway via `MCPPool` — NOT separate compose services. Document `cloudflared` setup separately at `deploy/cloudflared.example.yml`.

### 4.8 Tests

| File | Coverage |
|---|---|
| `tests/mcp/test_gateway_auth.py` | valid CF JWT → 200, missing header → 401, wrong AUD → 401, expired JWT → 401, malformed JWT → 401. Mock the JWKS fetch. |
| `tests/mcp/test_gateway_cors.py` | allowlisted origin preflight → 200, disallowed → 403, credentials handling. |
| `tests/mcp/test_gateway_query.py` | end-to-end `/mcp/query` returns multi-source provenance citations (mock the pool). |
| `tests/mcp/test_gateway_degraded.py` | source marked unavailable → response has `degraded:true` + `missing_source` named. |
| `tests/wiki/test_filelock.py` | two concurrent writers serialize, no partial writes, lock timeout raises. |

---

## Locked decisions you cannot revisit (already in canonical plan §7)

- **CX16A** — Cloudflare Access end-to-end. **No bearer middleware.** No browser token-entry login UI (A2C is dead). Service tokens for writing apps; user auth for dashboard.
- **CX12A** — `filelock` library. NOT a routing-through-gateway scheme.
- **A3A** — Restart-on-crash already in `pool.py`. Don't re-implement; consume `pool.unavailable` for warnings.
- **A4A** — Cloudflare Access REQUIRED for production. Document this in deploy README.
- **A1B** — Per-source auto-section names (`evidence-literature`, `evidence-lab` etc.) — already enforced by `wiki/writer.py`. Gateway just forwards writes.
- **CX-3** — Query intents are user-job names: `reporting | know-how | insight | other`. Don't reintroduce the backend names (`mechanistic | evidence | relational | synthesis`) at the gateway boundary — those are internal mappings.

---

## Out of scope (TODO/later, NOT Step 4)

- Multi-user auth, audit log, per-user permissions → V3.
- LRU query cache → TODO-3 in `TODOS.md`.
- Shared-drive filesystem-watch connector → TODO-1.
- End-to-end report-task eval suite → TODO-2.
- Step 5 reference writing-app clients (Claude Desktop config + IDE config + Python client) — the canonical plan groups Step 5 separately. You CAN do Step 5 in the same branch if scope feels right; otherwise leave for a follow-up.

---

## Acceptance for Step 4 done

1. `uv run llm-rag serve --port 8443` starts the gateway.
2. `cloudflared tunnel run` exposes it; manual test: `curl -H "CF-Access-Client-Id: ..." -H "CF-Access-Client-Secret: ..." https://<gateway-host>/mcp/query -d '{"query":"..."}'` returns provenance-tagged result. Same call without service-token headers returns 401 from Cloudflare.
3. Killing one of the source-server subprocesses mid-flight does NOT 500 the gateway — either recovery succeeds or response is degraded with the missing source named.
4. Two concurrent wiki writes (one from literature, one from lab) serialize via filelock; no partial writes.
5. All 723 existing tests still green; new gateway test files all green.
6. ruff clean on the new files (`src/llm_rag/mcp/gateway.py`, `tests/mcp/test_gateway_*.py`, `tests/wiki/test_filelock.py`).
7. `docker-compose up` brings up gateway + dashboard + chroma.

---

## Useful one-liners

```bash
# Run the federated source through the new pool to sanity-check
uv run python -c "
import asyncio
from llm_rag.mcp.pool import MCPPool
async def main():
    async with MCPPool.from_yaml('config/mcp-sources.yaml') as pool:
        print('Sources:', list(pool._sessions.keys()))
        print('Unavailable:', pool.unavailable)
asyncio.run(main())
"

# Full test suite + ruff + mypy
uv run pytest tests/ -v && uv run ruff check src/ tests/ && uv run mypy src/

# Snapshot regression net (must stay green throughout Step 4)
uv run pytest tests/snapshots/ -v
```
