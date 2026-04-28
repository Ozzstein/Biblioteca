"""Lab source server — scoped MCP tool surface for internal lab docs.

Provides the v0.1 source contract for SOPs, meetings, and internal reports.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from llm_rag.mcp.corpus_io import (
    get_chunks as _corpus_get_chunks,
)
from llm_rag.mcp.corpus_io import (
    get_manifest as _corpus_get_manifest,
)
from llm_rag.mcp.corpus_io import (
    search_chunks as _corpus_search_chunks,
)
from llm_rag.mcp.graph_io import (
    get_canonical as _graph_get_canonical,
)
from llm_rag.mcp.graph_io import (
    get_entity as _graph_get_entity,
)
from llm_rag.mcp.graph_io import (
    get_neighbors as _graph_get_neighbors,
)
from llm_rag.mcp.graph_io import (
    list_entities as _graph_list_entities,
)
from llm_rag.mcp.sources.mock import MockSource
from llm_rag.mcp.wiki_io import (
    get_template as _wiki_get_template,
)
from llm_rag.mcp.wiki_io import (
    list_pages as _wiki_list_pages,
)
from llm_rag.mcp.wiki_io import (
    read_page as _wiki_read_page,
)

app = FastMCP("lab")

_LAB_DOC_TYPES = {"sop", "meeting", "report"}
_LAB_DOC_PREFIXES = ("sop/", "meetings/", "meeting/", "reports/", "report/")
_LAB_WIKI_PREFIXES = (
    "sop/",
    "meetings/",
    "reports/",
    "internal-report/",
    "internal-reports/",
)


def _looks_like_lab_doc_id(doc_id: str) -> bool:
    lowered = doc_id.lower()
    return lowered.startswith(_LAB_DOC_PREFIXES)


def _is_lab_manifest(manifest: dict[str, Any] | None) -> bool:
    if not manifest:
        return False
    return str(manifest.get("doc_type", "")).lower() in _LAB_DOC_TYPES


def _is_lab_page(relative_path: str) -> bool:
    lowered = relative_path.lower()
    return lowered.startswith(_LAB_WIKI_PREFIXES)


@app.tool()
async def get_chunks(doc_id: str) -> list[dict[str, Any]]:
    if not _looks_like_lab_doc_id(doc_id):
        return []
    return await _corpus_get_chunks(doc_id)


@app.tool()
async def get_manifest(doc_id: str) -> dict[str, Any] | None:
    manifest = await _corpus_get_manifest(doc_id)
    if _is_lab_manifest(manifest):
        return manifest
    return None


@app.tool()
async def read_page(relative_path: str) -> str:
    if not _is_lab_page(relative_path):
        raise FileNotFoundError(f"Lab wiki page not found: {relative_path}")
    return await _wiki_read_page(relative_path)


@app.tool()
async def list_pages(subdir: str = "") -> list[str]:
    pages = await _wiki_list_pages(subdir)
    return [p for p in pages if _is_lab_page(p)]


@app.tool()
async def get_entity(entity_id: str) -> dict[str, Any] | None:
    return await _graph_get_entity(entity_id)


@app.tool()
async def list_entities(entity_type: str = "") -> list[dict[str, Any]]:
    return await _graph_list_entities(entity_type)


@app.tool()
async def get_neighbors(entity_id: str, depth: int = 1) -> list[str]:
    return await _graph_get_neighbors(entity_id, depth)


@app.tool()
async def search_chunks(query: str, n_results: int = 5) -> list[dict[str, Any]]:
    chunks = await _corpus_search_chunks(query, n_results=max(n_results * 3, n_results))
    filtered = [chunk for chunk in chunks if _looks_like_lab_doc_id(str(chunk.get("doc_id", "")))]
    if n_results < 1:
        return []
    return filtered[:n_results]


@app.tool()
async def get_template(page_type: str) -> str:
    return await _wiki_get_template(page_type)


@app.tool()
async def get_canonical(alias: str) -> str | None:
    return await _graph_get_canonical(alias)


def make_lab_reference_source() -> MockSource:
    """Reference in-memory lab source for conformance tests."""
    return MockSource(
        chunks={
            "sop/SOP-001": [
                {
                    "doc_id": "sop/SOP-001",
                    "chunk_index": 0,
                    "text": "SOP-001 requires PPE and calibrated balances.",
                    "section": "scope",
                }
            ]
        },
        manifests={
            "sop/SOP-001": {
                "doc_id": "sop/SOP-001",
                "source_path": "raw/sop/SOP-001.md",
                "content_hash": "sha256:mock",
                "doc_type": "sop",
                "source_connector": "manual",
                "fetched_at": "2026-01-01T00:00:00Z",
                "last_processed": "2026-01-01T00:00:00Z",
                "stages_completed": ["ingested"],
                "error": None,
            }
        },
        pages={
            "sop/SOP-001/index.md": "# SOP-001\n",
            "sop/SOP-001/v1.md": "# SOP-001 v1\n",
        },
        entities={
            "sop:SOP-001:v1": {
                "entity_type": "SOP",
                "canonical_name": "SOP-001 v1",
            }
        },
        edges={
            "sop:SOP-001:v1": [],
        },
        aliases={
            "sop-001": "sop:SOP-001:v1",
        },
        templates={
            "sop": "# {{ canonical_name }}\n",
        },
        search_results=[
            {
                "text": "SOP excerpt",
                "doc_id": "sop/SOP-001",
                "chunk_index": 0,
                "section": "scope",
            }
        ],
    )


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
