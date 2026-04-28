"""Reference MockSource implementation for the federation contract v0.1.

A minimal in-memory MCP source that satisfies the mandatory tool surface
defined in ``docs/mcp-source-protocol-v0.1.md`` §3.1. Used by:

1. The conformance suite (``tests/contracts/test_source_conformance.py``)
   as the baseline that any source — including the production literature
   source and the future sister experimental-data source — must match
   structurally.
2. The sister experimental-data project as a starting point. Copy this
   file, replace the in-memory ``_data`` dict with the real backend,
   re-run the conformance suite, ship.

This module exposes the tool functions directly (not as a runnable
FastMCP subprocess). Real sources expose both: a FastMCP app for
subprocess deployment AND importable async functions for in-process
conformance testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockSource:
    """In-memory source backing for the conformance suite.

    Construct with optional seed data; call ``register_tools()`` to get a
    dict of ``{tool_name: async_callable}`` ready to feed into the
    conformance suite.

    The fields use plain dicts (not the production Pydantic schemas) on
    purpose: a real third-party source might marshal its data through
    other types entirely. The contract is the **shape** of the tool
    return values, not the storage type.
    """

    chunks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    """doc_id -> list of chunk dicts."""

    manifests: dict[str, dict[str, Any]] = field(default_factory=dict)
    """doc_id -> manifest dict (or absent)."""

    pages: dict[str, str] = field(default_factory=dict)
    """relative_path -> markdown content."""

    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    """entity_id -> attribute dict (entity_type field included)."""

    edges: dict[str, list[str]] = field(default_factory=dict)
    """source_entity_id -> list of target_entity_ids (out-edges)."""

    aliases: dict[str, str] = field(default_factory=dict)
    """alias string -> canonical entity_id (optional, for get_canonical)."""

    templates: dict[str, str] = field(default_factory=dict)
    """page_type -> template markdown (optional, for get_template)."""

    search_results: list[dict[str, Any]] = field(default_factory=list)
    """Stub return for search_chunks if advertised; first n_results returned."""

    # ------------------------------------------------------------------
    # Mandatory tools (v0.1 §3.1)
    # ------------------------------------------------------------------

    async def get_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        """Read chunks for a document. Empty list when missing (no exception)."""
        return list(self.chunks.get(doc_id, []))

    async def get_manifest(self, doc_id: str) -> dict[str, Any] | None:
        """Read the manifest. ``None`` when missing."""
        manifest = self.manifests.get(doc_id)
        return dict(manifest) if manifest is not None else None

    async def read_page(self, relative_path: str) -> str:
        """Read a wiki page. ``FileNotFoundError`` when missing (mirrors production)."""
        if relative_path not in self.pages:
            raise FileNotFoundError(f"Wiki page not found: {relative_path}")
        return self.pages[relative_path]

    async def list_pages(self, subdir: str = "") -> list[str]:
        """List page paths, optionally filtered by ``subdir`` prefix."""
        if not subdir:
            return list(self.pages.keys())
        prefix = subdir.rstrip("/") + "/"
        return [p for p in self.pages if p.startswith(prefix) or p == subdir]

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Read entity attributes. ``None`` when missing.

        Returned dict carries an ``entity_id`` field for parity with the
        production source.
        """
        attrs = self.entities.get(entity_id)
        if attrs is None:
            return None
        result = dict(attrs)
        result["entity_id"] = entity_id
        return result

    async def list_entities(self, entity_type: str = "") -> list[dict[str, Any]]:
        """List entities, optionally filtered by ``entity_type``."""
        out: list[dict[str, Any]] = []
        for eid, attrs in self.entities.items():
            if entity_type and attrs.get("entity_type") != entity_type:
                continue
            entry = dict(attrs)
            entry["entity_id"] = eid
            out.append(entry)
        return out

    async def get_neighbors(self, entity_id: str, depth: int = 1) -> list[str]:
        """Out-edge neighbours within ``depth`` hops (BFS, dedup)."""
        if entity_id not in self.entities:
            return []
        if depth <= 1:
            return list(self.edges.get(entity_id, []))
        visited: set[str] = {entity_id}
        frontier: set[str] = set(self.edges.get(entity_id, []))
        visited.update(frontier)
        for _ in range(depth - 1):
            next_frontier: set[str] = set()
            for node in frontier:
                for nbr in self.edges.get(node, []):
                    if nbr not in visited:
                        visited.add(nbr)
                        next_frontier.add(nbr)
            frontier = next_frontier
        visited.discard(entity_id)
        return list(visited)

    # ------------------------------------------------------------------
    # Optional tools (v0.1 §3.2) — gated on capability advertisement
    # ------------------------------------------------------------------

    async def search_chunks(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Stub similarity search — returns the first ``n_results`` of seeded results."""
        if n_results < 1:
            return []
        return list(self.search_results[:n_results])

    async def get_template(self, page_type: str) -> str:
        """Look up a wiki template by page type. ``KeyError`` when unknown."""
        if page_type not in self.templates:
            raise FileNotFoundError(f"No template for page type: {page_type}")
        return self.templates[page_type]

    async def get_canonical(self, alias: str) -> str | None:
        """Resolve an alias to a canonical entity id. ``None`` when unknown."""
        return self.aliases.get(alias)

    # ------------------------------------------------------------------
    # Conformance plumbing
    # ------------------------------------------------------------------

    def register_tools(self) -> dict[str, Any]:
        """Return a name -> async-callable map for the conformance suite.

        Optional tools are included only when their backing data has been
        seeded (mirrors the "advertise via capability" model from the
        protocol spec).
        """
        tools: dict[str, Any] = {
            "get_chunks": self.get_chunks,
            "get_manifest": self.get_manifest,
            "read_page": self.read_page,
            "list_pages": self.list_pages,
            "get_entity": self.get_entity,
            "list_entities": self.list_entities,
            "get_neighbors": self.get_neighbors,
        }
        if self.search_results:
            tools["search_chunks"] = self.search_chunks
        if self.templates:
            tools["get_template"] = self.get_template
        if self.aliases:
            tools["get_canonical"] = self.get_canonical
        return tools


# ---------------------------------------------------------------------------
# Pre-seeded reference instance for tests + sister-project starter
# ---------------------------------------------------------------------------


def make_reference_source() -> MockSource:
    """Construct a MockSource with deterministic seed data.

    Used by the conformance suite so the baseline assertions don't depend
    on hand-crafting data per test. Sister-project authors can use this as
    a literal example of "what a populated source looks like."
    """
    src = MockSource(
        chunks={
            "papers/sample-001": [
                {
                    "doc_id": "papers/sample-001",
                    "chunk_index": 0,
                    "text": "Sample chunk one.",
                    "section": "intro",
                    "page": 1,
                    "token_count": 4,
                },
                {
                    "doc_id": "papers/sample-001",
                    "chunk_index": 1,
                    "text": "Sample chunk two.",
                    "section": "results",
                    "page": 2,
                    "token_count": 4,
                },
            ],
        },
        manifests={
            "papers/sample-001": {
                "doc_id": "papers/sample-001",
                "source_path": "raw/papers/sample-001.md",
                "content_hash": "sha256:mock",
                "doc_type": "paper",
                "source_connector": "manual",
                "fetched_at": "2026-01-01T00:00:00Z",
                "last_processed": "2026-01-01T00:00:00Z",
                "stages_completed": ["ingested", "extracted"],
                "error": None,
            },
        },
        pages={
            "index.md": "# Index\n",
            "materials/sample.md": "# Sample Material\n",
        },
        entities={
            "material:sample": {
                "entity_type": "Material",
                "canonical_name": "Sample",
            },
            "mechanism:sample-mech": {
                "entity_type": "FailureMechanism",
                "canonical_name": "Sample Mechanism",
            },
            "project:demo": {
                "entity_type": "Project",
                "canonical_name": "Demo",
            },
        },
        edges={
            "mechanism:sample-mech": ["material:sample"],
            "material:sample": ["project:demo"],
        },
        aliases={
            "sample-material": "material:sample",
        },
        templates={
            "material": "# {{ canonical_name }}\n",
        },
        search_results=[
            {
                "text": "matching chunk",
                "doc_id": "papers/sample-001",
                "chunk_index": 0,
                "section": "intro",
            }
        ],
    )
    return src
