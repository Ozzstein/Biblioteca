"""T1A — MCP tool-surface snapshot regression suite.

Captures byte-equivalent outputs from every read-only MCP tool against a
deterministic mini-corpus. The Step 1 source-server refactor must not change
any of these outputs. To re-baseline (e.g., after an intentional contract
change), re-run with::

    UPDATE_SNAPSHOTS=1 uv run pytest tests/snapshots/ -v

Without that env var, mismatches fail the test.

Tools NOT snapshotted here:
- ``corpus_io.search_chunks`` — depends on Chroma + sentence-transformers
  embedding determinism, which is hardware/version sensitive. A separate
  structural test (returns shape, fields present) can cover it.
- All write-side tools — covered by their own behavioral tests in
  ``tests/mcp/`` (snapshots would mutate state).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest


SNAPSHOT_DIR = Path(__file__).parent / "fixtures"
SNAPSHOT_DIR.mkdir(exist_ok=True)


def _normalize_paths(value: Any, root: Path) -> Any:
    """Replace absolute paths under ``root`` with ``<ROOT>``-prefixed strings.

    Snapshot fixtures are committed to the repo and must not contain
    machine-specific tmp_path values. ``scan_pending_files`` returns absolute
    paths; this helper makes them portable.
    """
    if isinstance(value, str):
        return value.replace(str(root), "<ROOT>")
    if isinstance(value, list):
        return [_normalize_paths(v, root) for v in value]
    if isinstance(value, dict):
        return {k: _normalize_paths(v, root) for k, v in value.items()}
    return value


def assert_snapshot(name: str, actual: Any) -> None:
    """Compare ``actual`` to ``fixtures/<name>.json``; write fixture if env-var set."""
    fixture_path = SNAPSHOT_DIR / f"{name}.json"
    serialized = json.dumps(actual, indent=2, sort_keys=True, default=str)

    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        fixture_path.write_text(serialized + "\n")
        return

    if not fixture_path.exists():
        pytest.fail(
            f"No snapshot fixture for {name!r}. "
            f"Run with UPDATE_SNAPSHOTS=1 to capture: "
            f"\n\nUPDATE_SNAPSHOTS=1 uv run pytest tests/snapshots/ -v"
        )

    expected = json.loads(fixture_path.read_text())
    if actual != expected:
        diff_summary = (
            f"\nExpected (from {fixture_path.name}):\n"
            f"{json.dumps(expected, indent=2, sort_keys=True, default=str)[:1000]}\n\n"
            f"Actual:\n{serialized[:1000]}"
        )
        pytest.fail(f"Snapshot mismatch for {name!r}.{diff_summary}")


# ---------------------------------------------------------------------------
# corpus-io snapshots (8)
# ---------------------------------------------------------------------------


async def test_snapshot_corpus_get_chunks_known(mini_corpus: Path) -> None:
    from llm_rag.mcp.corpus_io import get_chunks

    result = await get_chunks("papers/sample-lfp-001")
    assert_snapshot("corpus__get_chunks__known", result)


async def test_snapshot_corpus_get_chunks_missing(mini_corpus: Path) -> None:
    from llm_rag.mcp.corpus_io import get_chunks

    result = await get_chunks("papers/no-such-doc")
    assert_snapshot("corpus__get_chunks__missing", result)


async def test_snapshot_corpus_get_manifest_known(mini_corpus: Path) -> None:
    from llm_rag.mcp.corpus_io import get_manifest

    result = await get_manifest("papers/sample-lfp-001")
    assert_snapshot("corpus__get_manifest__known", result)


async def test_snapshot_corpus_get_manifest_missing(mini_corpus: Path) -> None:
    from llm_rag.mcp.corpus_io import get_manifest

    result = await get_manifest("papers/no-such-doc")
    assert_snapshot("corpus__get_manifest__missing", result)


async def test_snapshot_corpus_list_pending_extracted(mini_corpus: Path) -> None:
    from llm_rag.mcp.corpus_io import list_pending_docs

    result = sorted(await list_pending_docs("extracted"))
    assert_snapshot("corpus__list_pending__extracted", result)


async def test_snapshot_corpus_list_pending_graph_updated(mini_corpus: Path) -> None:
    from llm_rag.mcp.corpus_io import list_pending_docs

    result = sorted(await list_pending_docs("graph_updated"))
    assert_snapshot("corpus__list_pending__graph_updated", result)


async def test_snapshot_corpus_get_export_known(mini_corpus: Path) -> None:
    from llm_rag.mcp.corpus_io import get_export

    result = await get_export("papers/sample-lfp-001")
    assert_snapshot("corpus__get_export__known", result)


async def test_snapshot_corpus_scan_pending(mini_corpus: Path) -> None:
    from llm_rag.mcp.corpus_io import scan_pending_files

    result = await scan_pending_files()
    # Sort + path-normalize for cross-machine portability.
    normalized = {
        "pending_paths": sorted(_normalize_paths(result["pending_paths"], mini_corpus))
    }
    assert_snapshot("corpus__scan_pending", normalized)


# ---------------------------------------------------------------------------
# wiki-io snapshots (5)
# ---------------------------------------------------------------------------


async def test_snapshot_wiki_read_index(mini_corpus: Path) -> None:
    from llm_rag.mcp.wiki_io import read_page

    result = await read_page("index.md")
    assert_snapshot("wiki__read_page__index", result)


async def test_snapshot_wiki_read_material(mini_corpus: Path) -> None:
    from llm_rag.mcp.wiki_io import read_page

    result = await read_page("materials/lfp.md")
    assert_snapshot("wiki__read_page__lfp", result)


async def test_snapshot_wiki_list_pages_root(mini_corpus: Path) -> None:
    from llm_rag.mcp.wiki_io import list_pages

    result = sorted(await list_pages())
    assert_snapshot("wiki__list_pages__root", result)


async def test_snapshot_wiki_list_pages_materials(mini_corpus: Path) -> None:
    from llm_rag.mcp.wiki_io import list_pages

    result = sorted(await list_pages("materials"))
    assert_snapshot("wiki__list_pages__materials", result)


async def test_snapshot_wiki_get_template_material(mini_corpus: Path) -> None:
    from llm_rag.mcp.wiki_io import get_template

    result = await get_template("material")
    assert_snapshot("wiki__get_template__material", result)


# ---------------------------------------------------------------------------
# graph-io snapshots (7)
# ---------------------------------------------------------------------------


async def test_snapshot_graph_get_entity_known(mini_corpus: Path) -> None:
    from llm_rag.mcp.graph_io import get_entity

    result = await get_entity("material:lfp")
    assert_snapshot("graph__get_entity__known", result)


async def test_snapshot_graph_get_entity_missing(mini_corpus: Path) -> None:
    from llm_rag.mcp.graph_io import get_entity

    result = await get_entity("material:no-such")
    assert_snapshot("graph__get_entity__missing", result)


async def test_snapshot_graph_list_entities_all(mini_corpus: Path) -> None:
    from llm_rag.mcp.graph_io import list_entities

    result = sorted(await list_entities(), key=lambda e: e["entity_id"])
    assert_snapshot("graph__list_entities__all", result)


async def test_snapshot_graph_list_entities_material(mini_corpus: Path) -> None:
    from llm_rag.mcp.graph_io import list_entities

    result = sorted(await list_entities("Material"), key=lambda e: e["entity_id"])
    assert_snapshot("graph__list_entities__material", result)


async def test_snapshot_graph_get_neighbors_depth1(mini_corpus: Path) -> None:
    from llm_rag.mcp.graph_io import get_neighbors

    result = sorted(await get_neighbors("mechanism:sei", depth=1))
    assert_snapshot("graph__get_neighbors__sei_d1", result)


async def test_snapshot_graph_get_neighbors_depth2(mini_corpus: Path) -> None:
    from llm_rag.mcp.graph_io import get_neighbors

    result = sorted(await get_neighbors("mechanism:sei", depth=2))
    assert_snapshot("graph__get_neighbors__sei_d2", result)


async def test_snapshot_graph_get_canonical_known(mini_corpus: Path) -> None:
    from llm_rag.mcp.graph_io import get_canonical

    result = await get_canonical("lithium iron phosphate")
    assert_snapshot("graph__get_canonical__alias_known", result)


async def test_snapshot_graph_get_canonical_missing(mini_corpus: Path) -> None:
    from llm_rag.mcp.graph_io import get_canonical

    result = await get_canonical("nonexistent-alias")
    assert_snapshot("graph__get_canonical__alias_missing", result)
