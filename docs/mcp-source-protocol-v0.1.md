# MCP Source-Server Protocol v0.1

**Status:** Draft (v0.1)
**Date:** 2026-04-27
**Audience:** Anyone implementing a knowledge-source MCP server that the
Battery Research OS gateway will federate over.

This document is the contract any MCP source-server must satisfy to plug
into the federated gateway from Step 4 of the V2 lab-knowledge plan. It is
**versioned** (semver) and **negotiated** (sources declare their
capabilities, the gateway routes accordingly).

For the architectural rationale see
`docs/superpowers/plans/2026-04-27-v2-lab-knowledge-extension.md` §6.2.

---

## 1. Versioning policy

- The protocol version is encoded in `config/mcp-sources.yaml` at
  `protocol_version`. The MCPPool refuses to load a registry whose version
  it does not understand, so the gateway and the registry move together.
- Breaking changes to the tool surface, capability vocabulary, or registry
  schema bump the protocol minor version (`0.1` → `0.2`, etc.). The gateway
  publishes a compatibility window: at minimum **N-1** support, i.e. when
  v0.2 ships, v0.1 sources continue to work for one full release cycle.
- Non-breaking additions (new optional fields, new optional tools, new
  capability strings that the gateway already ignores when absent) do
  **not** bump the version.

A source declares the protocol version it implements via its
`config/mcp-sources.yaml` registry entry; this is the gateway's only
trustworthy signal — the source process itself is not interrogated for
its version.

---

## 2. Registry schema (v0.1)

A YAML file with this shape:

```yaml
protocol_version: "0.1"

sources:
  - name: <unique source name, lowercase, alphanumeric + hyphen>
    backend: stdio                    # only "stdio" supported in v0.1
    command: [<argv>, ...]            # required for stdio backend
    env:                              # optional
      KEY: "value"
    capabilities:                     # optional but strongly recommended
      - <capability string>
```

Validation rules (enforced by `load_servers_from_yaml`):

| Field | Rule |
|---|---|
| `protocol_version` | Must equal `"0.1"`. Other values raise `ValueError`. |
| `sources` | Must be a non-empty list. |
| `sources[].name` | Required string. Unique across the file. |
| `sources[].backend` | Must be `"stdio"` in v0.1. (`"http"` is reserved for future.) |
| `sources[].command` | Required for stdio backend; list of strings (argv). The literal token `"python"` is rewritten to the parent process's `sys.executable` so the subprocess inherits the active venv. |
| `sources[].env` | Optional mapping of string → string. |
| `sources[].capabilities` | Optional list of strings; see §4 for the vocabulary. |

Anything outside this schema MUST be ignored by v0.1 loaders, so future
extensions can land without breaking older gateways.

---

## 3. Required tool surface

A v0.1 source MUST implement the following MCP tools by name. Tool names,
parameter names, and result shapes are part of the contract — **byte-equivalence
is enforced via the `tests/snapshots/` suite for the production literature
source and via the `tests/contracts/` suite for any source.**

### 3.1 Mandatory tools

| Tool | Purpose | Async | Signature |
|---|---|---|---|
| `get_chunks` | Read chunked text for a document. | yes | `(doc_id: str) -> list[dict]` |
| `get_manifest` | Read the DocumentManifest sidecar. | yes | `(doc_id: str) -> dict \| None` |
| `read_page` | Read a wiki page's full markdown. | yes | `(relative_path: str) -> str` |
| `list_pages` | List wiki pages, optionally under a subdir. | yes | `(subdir: str = "") -> list[str]` |
| `get_entity` | Read graph node attributes. | yes | `(entity_id: str) -> dict \| None` |
| `list_entities` | List graph entities, optionally filtered by type. | yes | `(entity_type: str = "") -> list[dict]` |
| `get_neighbors` | Out-edge neighbours within `depth` hops. | yes | `(entity_id: str, depth: int = 1) -> list[str]` |

These seven cover the read surface a query planner needs to answer
`reporting`, `know-how`, and `insight` intents.

### 3.2 Optional tools

A source MAY additionally implement:

- `search_chunks(query: str, n_results: int = 5) -> list[dict]` — semantic
  similarity search. Sources that don't have a vector store should omit
  this and not advertise the corresponding capability.
- `get_template(page_type: str) -> str` — wiki page template lookup.
- `get_canonical(alias: str) -> str | None` — alias → canonical entity id.

The conformance suite checks mandatory tools strictly; optional tools are
checked only if the source advertises them.

### 3.3 Write-side tools

`save_manifest`, `save_export`, `ingest_file`, `write_auto_sections`,
`create_page`, `write_provenance`, `materialize_page`, `merge_extraction`,
`merge_by_doc_id`, `materialize_from_claims` are all **internal-only** in
v0.1 — they live on the literature source for backwards compatibility with
the existing pipeline but are **not** part of the federation contract. The
gateway never forwards write calls from external agentic clients.

---

## 4. Capability vocabulary

Capabilities are advertised in the registry's `capabilities:` list and
consumed by the gateway's intent router (Step 4). They are advisory for
v0.1 — the gateway uses them to decide which sources to fan out to for a
given query intent. A source's capability list is also surfaced in
`pool.configs[i].capabilities` for inspection.

Three string namespaces are defined:

- `tool:<name>` — declares that a specific tool is implemented. Required
  for the mandatory tools (otherwise the conformance suite skips checking
  them, which is a smell).
- `intent:<name>` — declares that this source can usefully answer queries
  of the named intent. v0.1 vocabulary: `reporting`, `know-how`,
  `insight`. Sources with no useful answer for a given intent should
  simply omit it — the gateway will exclude them from fan-out.
- `tag:<name>` — declares the kinds of documents this source owns.
  v0.1 vocabulary: `paper`, `sop`, `meeting`, `report`. Tag-based filtering
  is the primary mechanism for routing typed queries (e.g., "find our SOP
  for X" → tag:sop).

Unknown namespaces MUST be ignored by v0.1 gateways so future routing
strategies can land non-breaking.

---

## 5. Conformance test suite

Live at `tests/contracts/test_source_conformance.py`. The suite is
parameterised: pass in any `Source`-compatible object (today: a callable
that returns a dict-of-async-tools), and the suite asserts:

1. The mandatory tool names from §3.1 are all present.
2. Each mandatory tool accepts the documented parameters and returns a
   value of the documented shape (lists, strings, optional dicts).
3. Each tool's "missing input" path returns the documented neutral value
   (`[]`, `None`) rather than raising.
4. If `search_chunks` is advertised via `tool:search_chunks` capability,
   it conforms structurally as well.
5. The reference `MockSource` (next section) passes the suite from a clean
   import. Any new source that diverges from MockSource's interface will
   fail this baseline.

The conformance suite does **not** assert byte-equivalent output (that's
T1A's job for the production source). It only enforces the structural
contract, so genuinely different sources (lab vs literature, sister
project) can pass it with their own data.

---

## 6. Reference implementation: MockSource

`src/llm_rag/mcp/sources/mock.py` ships a minimal in-memory source that:

- Implements every mandatory tool with deterministic stub behavior.
- Maintains a tiny in-memory wiki + graph + manifest store, populated at
  construction time.
- Is used by the conformance suite (above) as the "did we break the
  baseline" canary.
- Is the recommended starting point for the sister experimental-data
  project — copy it, replace the in-memory storage with the real backend,
  re-run the conformance suite.

MockSource is intentionally NOT decorated with `@app.tool()` and NOT
runnable as a subprocess. It exposes the tool functions directly so the
conformance suite can call them in-process. Real sources (literature, lab,
sister) MUST also expose their tool functions importably so the
conformance suite can be run against them without spawning subprocesses.

---

## 7. What v0.1 deliberately does NOT cover

- **HTTP backend.** Reserved for Step 4's gateway exposing source servers
  to external clients. Stdio-only for now.
- **Streaming responses.** All v0.1 tools return whole-result values.
- **Authentication between gateway and sources.** Sources trust the
  gateway via the local subprocess boundary (gateway is the parent process
  spawning them); cross-host auth is Step 4's gateway concern at the edge.
- **Mutation tools as part of the contract.** Write tools live on the
  literature source for backward-compat with the existing pipeline but
  are not exposed externally.
- **Capability negotiation handshake at runtime.** Capabilities are
  declared statically in the registry. The runtime gateway inspects them
  but does not interrogate the source process for them; this keeps v0.1
  simple at the cost of requiring a registry edit when a source adds a
  capability.

These are candidates for v0.2 once concrete pain points emerge from
real usage.

---

## 8. How to plug a new source into the gateway (operator's quick guide)

1. Implement the §3.1 mandatory tools as MCP tools on a FastMCP app named
   after your source (e.g., `FastMCP("experiments")`). Reference: copy
   `src/llm_rag/mcp/sources/mock.py` for the surface; replace the storage.
2. Add an entry point so your server is runnable:
   `python -m your_package.your_source`.
3. Add an entry to `config/mcp-sources.yaml`:
   ```yaml
   - name: experiments
     backend: stdio
     command: ["python", "-m", "your_package.your_source"]
     capabilities:
       - "intent:insight"
       - "tag:experiment"
       - "tool:get_chunks"
       - "tool:get_entity"
       - "tool:list_entities"
       - "tool:get_neighbors"
       - "tool:read_page"
       - "tool:list_pages"
       - "tool:get_manifest"
   ```
4. Run the conformance suite against your in-process tool functions:
   `uv run pytest tests/contracts/ -v --source-module your_package.your_source`.
5. The gateway picks up the new source on next restart (no code change
   needed).
