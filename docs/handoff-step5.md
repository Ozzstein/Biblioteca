# Handoff: Step 5 — Reference Writing-App Integrations + v1 API Spec

**Branch to land on:** `Ozzstein/lab-knowledge` (after Step 4 has merged) — or branch off as `Ozzstein/lab-knowledge-step5` and PR back.
**Authoritative plan:** `docs/superpowers/plans/2026-04-27-v2-lab-knowledge-extension.md` §9 Step 5
**Hard prerequisite:** Step 4 (gateway + auth + filelock) must be functional. The Python client connects to the gateway URL; the configs reference its hostname.
**Soft prerequisite:** Step 0a corpus curation gives the demo prompts something real to retrieve from. Without it, the end-to-end demo runs but returns empty/mock-ish results.

This brief is for whoever picks up Step 5 in another Conductor workspace. Read this; don't re-read three plan files.

---

## What you're building (one-paragraph version)

Three reference clients that demonstrate the V2 reporting workflow end-to-end, plus a stable agent-facing API spec. After Step 5 ships, a manager can: open Claude Desktop with the provided config, ask "draft a 3-page summary of LFP cathode degradation including our internal SOPs and reports," and get back drafted prose with provenance citations to both internal sources and published literature. Same outcome reproducible from Cursor and from a 50-line Python script.

---

## Sub-deliverables

### 5.1 Claude Desktop reference config

```
examples/writing-app/claude_desktop/
├── claude_desktop_config.json     # copy-pasteable MCP server config
└── README.md                      # setup steps + screenshot of expected behavior
```

`claude_desktop_config.json` shape (Claude Desktop reads `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "battery-research-os": {
      "url": "https://<your-gateway-hostname>",
      "headers": {
        "CF-Access-Client-Id": "${CF_ACCESS_CLIENT_ID}",
        "CF-Access-Client-Secret": "${CF_ACCESS_CLIENT_SECRET}"
      }
    }
  }
}
```

Note: Claude Desktop's HTTP MCP support has evolved fast — verify the current schema in the official docs at the time of implementation. If the field shape has changed, follow current docs and update the example accordingly.

### 5.2 Cursor / IDE-style reference config

```
examples/writing-app/cursor/
├── .cursor/mcp.json               # Cursor MCP config
└── README.md                      # add to project's .cursor/mcp.json
```

Cursor (and Continue, by extension) read `.cursor/mcp.json` per-project. Same auth headers as Claude Desktop. Document that this config can live at the project level OR globally at `~/.cursor/mcp.json` for personal use.

### 5.3 Custom Python agent

```
examples/writing-app/python/
├── client.py                      # ~50-line demo script
├── pyproject.toml                 # standalone deps (mcp, httpx, anthropic-sdk)
├── .env.example                   # CF_ACCESS_CLIENT_ID/SECRET, GATEWAY_URL
└── README.md                      # how to run + expected output
```

`client.py` flow:
1. Reads `GATEWAY_URL`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` from env.
2. Connects to `<GATEWAY_URL>/mcp` via the MCP HTTP/SSE client (use `mcp` Python SDK).
3. Sends a query: `await session.call_tool("query", {"query": "draft a summary of LFP cathode degradation including our internal SOPs and reports"})`.
4. Prints drafted prose + provenance citations + which sources were consulted vs unavailable.
5. Exits 0 on success; nonzero on auth failure or gateway error.

This is the "smoke test" the user runs to confirm Step 4 works end-to-end. Keep it small enough to read in one screen.

### 5.4 v1 API spec — `docs/api/v1.md` (CX-9)

**Update 2026-04-28:** Step 4 agent shipped a thin v1 API spec already (~100 lines, covers auth + 5 routes + basic shapes). **Don't redo it from scratch — extend it.** See `docs/review-step4.md` §F1 for the specific gaps that block sister-project integration.

The stable agent-facing contract. Cover:

- **Authentication** — Cloudflare Access service tokens for machines, user identity for humans. Header names, JWT validation expectations, error codes (401 from edge, 403 from app).
- **Endpoints** — every gateway route the Step 4 agent shipped. For each: HTTP method, path, request schema, response schema, error model, idempotency notes.
- **Citation payload format** — the canonical shape of `citations` in `/mcp/query` responses. Include source name, doc_id, chunk index (or page), confidence, ingested_at (per CX13B), and verify-against-source flag.
- **Versioning policy** — semver (this is v1.0.0). Breaking changes bump major. Sister project / external integrators rely on this.
- **Streaming behavior** — for `/mcp/query`, document whether the answer streams (SSE chunks) or returns whole. If streaming, give a sample SSE event sequence.
- **Timeout semantics** — what the gateway promises to do if a source server doesn't respond in N seconds (likely returns degraded with `unavailable: ["<source>"]`).
- **Error model** — every error response shape. At minimum: 401 (auth), 403 (no service-token policy), 404 (unknown tool / route), 408 (gateway timeout), 503 (filelock timeout, all sources unavailable), 500 (unexpected — also include a `request_id` for correlation).
- **Out of scope for v1** — multi-tenant, write tools (per protocol §3.3), pagination (responses are whole-result in v1).

This file is a CONTRACT. Sister project ETA is 1–2 months — they integrate against this. Future API evolution bumps the version and ships `docs/api/v2.md` with a compatibility window.

### 5.5 Repo-level README pointer

Update repo `README.md` "External integrations" section (or add it) to link to `examples/writing-app/README.md` and `docs/api/v1.md`.

### 5.6 Tests

This step is mostly examples + docs; tests are light:

- `tests/examples/test_python_client_smoke.py` — imports `examples/writing-app/python/client.py`, mocks the MCP HTTP transport, asserts the client constructs the right URL + headers and calls the right tool. Does NOT spin up a real gateway.
- `tests/docs/test_api_spec_examples_parse.py` — every JSON example in `docs/api/v1.md` parses (catches typos in the spec).

---

## Locked decisions (already in canonical plan §7; you cannot revisit)

- **Three clients, not one** (resolved during /office-hours). Don't drop one to ship faster.
- **Claude Desktop, Cursor, Python — in that order of importance.** Claude Desktop is the primary demo target.
- **No bearer token in any config.** Auth is Cloudflare Access service tokens (CX16A). If the Step 4 agent shipped bearer middleware anyway (against the plan), flag it back to CTO before writing configs against it.
- **No reporting templates / cite_pack tools in Step 5** (CX1B). Report assembly is the writing app's job, not the gateway's. Keep `client.py` short — it's a demo of the existing query flow, not a report generator.
- **API spec is `docs/api/v1.md`** (singular). Don't split into per-endpoint files yet.

---

## What you can start NOW (parallel with Step 4)

These can be drafted before Step 4 lands as long as you treat the gateway shape as the published contract from `docs/handoff-step4.md` §4.3:

1. `docs/api/v1.md` — draft the spec from the handoff brief. Mark anything ambiguous as `TODO: confirm with Step 4 implementation`.
2. `examples/writing-app/python/client.py` skeleton + `.env.example` + README scaffolding.
3. `examples/writing-app/claude_desktop/README.md` — setup walkthrough text (the JSON config is mechanical).
4. `examples/writing-app/cursor/README.md` — same.
5. `tests/examples/test_python_client_smoke.py` skeleton.

What you CANNOT do until Step 4 lands:
- Run the actual end-to-end demo against a real gateway.
- Confirm the exact response shapes (in case Step 4 deviates from the handoff brief).
- Capture the screenshot for the Claude Desktop README (the demo working in real Claude Desktop).

---

## Acceptance for Step 5 done

1. From a fresh machine: install Claude Desktop, drop in `claude_desktop_config.json` with real CF Access credentials, ask the demo prompt, get back drafted prose with provenance citations to both literature and lab sources.
2. Same demo from Cursor with `.cursor/mcp.json`.
3. `python examples/writing-app/python/client.py` returns the same answer with provenance, run from a fresh venv (just `mcp`, `httpx`, `python-dotenv` installed).
4. `docs/api/v1.md` is complete: every gateway endpoint documented; every example valid JSON; sister-project author can build an MCP source against it without asking questions.
5. `tests/examples/test_python_client_smoke.py` and `tests/docs/test_api_spec_examples_parse.py` green.
6. `README.md` links to the examples + API spec.
7. CLAUDE.md "MCP Gateway" section (added in Step 6) cross-references Step 5 examples.

---

## Out of scope (TODO/later, NOT Step 5)

- Multi-user-aware client UX (currently single-user CF Access service token per integration).
- Streaming demo if Step 4 didn't ship streaming yet — note in the API spec as "v1.x future".
- Self-hosted Continue / other IDE configs beyond Cursor (one IDE example is enough; community can extend).
- Web-based playground / interactive docs site.
- Auto-generated client SDKs (the spec is Markdown; no OpenAPI generator yet).

---

## Useful one-liners

```bash
# Verify Step 4 is up before the demo
curl -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
     -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
     https://<gateway-host>/mcp/health

# Run the Python client smoke test (no real gateway needed)
uv run pytest tests/examples/test_python_client_smoke.py -v

# Validate every JSON example in the API spec parses
uv run pytest tests/docs/test_api_spec_examples_parse.py -v

# Manual end-to-end demo (real gateway required)
cd examples/writing-app/python
uv pip install -r requirements.txt   # or `uv sync` if pyproject.toml present
cp .env.example .env
# fill in CF_ACCESS_CLIENT_ID/SECRET + GATEWAY_URL
uv run python client.py
```

---

## Suggested commit shape

Three commits to keep the diff reviewable:

1. `docs: ship v1 API spec for the federated gateway` — `docs/api/v1.md` + the JSON-parse test.
2. `feat(examples): writing-app reference clients (Claude Desktop, Cursor, Python)` — the three example dirs + the smoke test.
3. `docs: link writing-app examples + v1 API spec from README + CLAUDE.md`.
