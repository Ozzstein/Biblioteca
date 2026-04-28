"""Federation contract v0.1 conformance suite.

Verifies that any MCP source server implements the mandatory tool surface
defined in ``docs/mcp-source-protocol-v0.1.md`` §3.1 with the documented
parameter and return shapes.

The suite is parametrised over a list of ``(label, tool_factory)`` pairs.
Each factory returns a ``dict[str, async_callable]`` of tool functions —
no subprocess spawning. New sources (the lab source from Step 2, the
sister experimental-data source) wire themselves in by appending to
``CONFORMANT_SOURCES`` below or by importing ``CONFORMANT_SOURCES`` and
extending it from a project-local conftest.

Mandatory tools checked (per protocol §3.1):

- ``get_chunks(doc_id) -> list[dict]``
- ``get_manifest(doc_id) -> dict | None``
- ``read_page(relative_path) -> str``
- ``list_pages(subdir="") -> list[str]``
- ``get_entity(entity_id) -> dict | None``
- ``list_entities(entity_type="") -> list[dict]``
- ``get_neighbors(entity_id, depth=1) -> list[str]``

Optional tools (``search_chunks``, ``get_template``, ``get_canonical``)
are checked structurally only when present in the tool dict.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from llm_rag.mcp.sources.lab import make_lab_reference_source
from llm_rag.mcp.sources.mock import make_reference_source

# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------


SourceFactory = Callable[[], dict[str, Callable[..., Awaitable[Any]]]]


def _mock_factory() -> dict[str, Callable[..., Awaitable[Any]]]:
    """Return tools from a freshly-seeded MockSource."""
    return make_reference_source().register_tools()


def _lab_factory() -> dict[str, Callable[..., Awaitable[Any]]]:
    """Return tools from a freshly-seeded lab reference source."""
    return make_lab_reference_source().register_tools()


CONFORMANT_SOURCES: list[tuple[str, SourceFactory]] = [
    ("mock", _mock_factory),
    ("lab", _lab_factory),
]
"""Sources to run the suite against. Step 2 will append ``("lab", ...)``;
the sister project appends its own. Add via ``CONFORMANT_SOURCES.append(...)``
in a project conftest if you can't modify this file."""


# ---------------------------------------------------------------------------
# Mandatory-tool presence
# ---------------------------------------------------------------------------


_MANDATORY_TOOLS = {
    "get_chunks",
    "get_manifest",
    "read_page",
    "list_pages",
    "get_entity",
    "list_entities",
    "get_neighbors",
}


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
def test_mandatory_tools_present(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    missing = _MANDATORY_TOOLS - set(tools)
    assert not missing, (
        f"source {label!r} missing mandatory v0.1 tools: {sorted(missing)}"
    )


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
def test_mandatory_tools_callable(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    for name in _MANDATORY_TOOLS:
        assert callable(tools[name]), f"source {label!r}: {name!r} is not callable"


# ---------------------------------------------------------------------------
# get_chunks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_get_chunks_returns_list(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    result = await tools["get_chunks"]("nonexistent/doc")
    assert isinstance(result, list), f"source {label!r}: get_chunks must return list"
    # Empty result for missing doc — must not raise.


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_get_chunks_empty_for_unknown(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    result = await tools["get_chunks"]("definitely/nope")
    assert result == [], (
        f"source {label!r}: get_chunks for unknown doc_id must return [], got {result!r}"
    )


# ---------------------------------------------------------------------------
# get_manifest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_get_manifest_none_for_unknown(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    result = await tools["get_manifest"]("nope/doc")
    assert result is None, (
        f"source {label!r}: get_manifest for unknown doc_id must return None"
    )


# ---------------------------------------------------------------------------
# read_page / list_pages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_read_page_raises_for_missing(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    with pytest.raises(FileNotFoundError):
        await tools["read_page"]("nope/page.md")


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_list_pages_returns_list_of_strings(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    result = await tools["list_pages"]()
    assert isinstance(result, list), f"source {label!r}: list_pages must return list"
    for entry in result:
        assert isinstance(entry, str), (
            f"source {label!r}: list_pages entries must be strings, got {entry!r}"
        )


# ---------------------------------------------------------------------------
# get_entity / list_entities
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_get_entity_none_for_unknown(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    result = await tools["get_entity"]("nope:entity")
    assert result is None, (
        f"source {label!r}: get_entity for unknown id must return None"
    )


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_list_entities_returns_list_of_dicts(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    result = await tools["list_entities"]()
    assert isinstance(result, list)
    for entry in result:
        assert isinstance(entry, dict), (
            f"source {label!r}: list_entities entries must be dicts, got {entry!r}"
        )
        assert "entity_id" in entry, (
            f"source {label!r}: list_entities entries must include 'entity_id'"
        )


# ---------------------------------------------------------------------------
# get_neighbors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_get_neighbors_returns_list_for_unknown(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    result = await tools["get_neighbors"]("nope:entity", 1)
    assert isinstance(result, list), (
        f"source {label!r}: get_neighbors must return list (got {type(result).__name__})"
    )
    assert result == [], (
        f"source {label!r}: get_neighbors for unknown entity must return []"
    )


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_get_neighbors_default_depth(
    label: str, factory: SourceFactory
) -> None:
    """Tools must accept depth as keyword OR positional with default 1."""
    tools = factory()
    # No depth arg — exercises the default
    result = await tools["get_neighbors"]("nope:entity")
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Optional tools — only when present
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_search_chunks_when_present(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    if "search_chunks" not in tools:
        pytest.skip(f"source {label!r} does not advertise search_chunks")
    result = await tools["search_chunks"]("any query", 3)
    assert isinstance(result, list)
    assert len(result) <= 3


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_search_chunks_zero_results_handled(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    if "search_chunks" not in tools:
        pytest.skip(f"source {label!r} does not advertise search_chunks")
    result = await tools["search_chunks"]("any", 0)
    assert result == [], (
        f"source {label!r}: search_chunks(n_results=0) must return []"
    )


@pytest.mark.parametrize(("label", "factory"), CONFORMANT_SOURCES)
async def test_get_canonical_when_present(
    label: str, factory: SourceFactory
) -> None:
    tools = factory()
    if "get_canonical" not in tools:
        pytest.skip(f"source {label!r} does not advertise get_canonical")
    # Unknown alias must return None, not raise
    result = await tools["get_canonical"]("definitely-unknown-alias-xyz")
    assert result is None


# ---------------------------------------------------------------------------
# MockSource baseline sanity (the contract canary)
# ---------------------------------------------------------------------------


async def test_mock_reference_round_trip() -> None:
    """End-to-end sanity check that the reference impl actually returns its seed data."""
    src = make_reference_source()
    tools = src.register_tools()

    chunks = await tools["get_chunks"]("papers/sample-001")
    assert len(chunks) == 2
    assert chunks[0]["text"] == "Sample chunk one."

    manifest = await tools["get_manifest"]("papers/sample-001")
    assert manifest is not None
    assert manifest["doc_id"] == "papers/sample-001"

    page = await tools["read_page"]("index.md")
    assert page.startswith("# Index")

    pages = await tools["list_pages"]()
    assert "index.md" in pages

    entity = await tools["get_entity"]("material:sample")
    assert entity is not None
    assert entity["canonical_name"] == "Sample"
    assert entity["entity_id"] == "material:sample"

    neighbours = await tools["get_neighbors"]("mechanism:sample-mech", depth=2)
    assert "material:sample" in neighbours
    assert "project:demo" in neighbours

    canon = await tools["get_canonical"]("sample-material")
    assert canon == "material:sample"
