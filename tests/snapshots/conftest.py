"""Mini-corpus fixture for the T1A MCP snapshot regression suite.

Sets up a deterministic mini-corpus in ``tmp_path`` and points ``Settings``
at it via ``ROOT_DIR``. Every snapshot test uses the same baseline so
fixtures are reproducible across machines.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Generator
from pathlib import Path

import networkx as nx
import pytest

from llm_rag.config import PROJECT_ROOT, get_settings

# ---------------------------------------------------------------------------
# Mini-corpus content
# ---------------------------------------------------------------------------

_SAMPLE_DOC_ID = "papers/sample-lfp-001"
_SAMPLE_DOC_TEXT = (
    "LFP cathodes show capacity fade after extended cycling.\n\n"
    "The dominant failure mechanism is loss of active lithium via SEI growth.\n\n"
    "At 25 C and 1C rate, capacity retention is typically 85% after 1000 cycles."
)

_SAMPLE_MANIFEST = {
    "doc_id": _SAMPLE_DOC_ID,
    "source_path": "raw/papers/sample-lfp-001.md",
    "content_hash": "sha256:fixed-deterministic-hash-for-snapshot-tests",
    "doc_type": "paper",
    "source_connector": "manual",
    "fetched_at": "2026-04-01T00:00:00Z",
    "last_processed": "2026-04-01T00:05:00Z",
    "stages_completed": ["ingested", "extracted"],
    "error": None,
    "title": "Capacity Fade in LFP",
    "authors": ["A. Researcher"],
    "doi": None,
    "arxiv_id": None,
}

_SAMPLE_PENDING_MANIFEST = {
    "doc_id": "papers/pending-doc",
    "source_path": "raw/papers/pending-doc.md",
    "content_hash": "sha256:pending-hash",
    "doc_type": "paper",
    "source_connector": "manual",
    "fetched_at": "2026-04-02T00:00:00Z",
    "last_processed": "2026-04-02T00:01:00Z",
    "stages_completed": ["ingested"],
    "error": None,
    "title": "Pending Doc",
    "authors": [],
    "doi": None,
    "arxiv_id": None,
}

_SAMPLE_CHUNKS = [
    {
        "doc_id": _SAMPLE_DOC_ID,
        "chunk_index": 0,
        "text": "LFP cathodes show capacity fade after extended cycling.",
        "section": "introduction",
        "page": 1,
        "token_count": 12,
    },
    {
        "doc_id": _SAMPLE_DOC_ID,
        "chunk_index": 1,
        "text": "The dominant failure mechanism is loss of active lithium via SEI growth.",
        "section": "results",
        "page": 1,
        "token_count": 14,
    },
]

_SAMPLE_EXPORT = {
    "doc_id": _SAMPLE_DOC_ID,
    "entities": [
        {
            "entity_id": "material:lfp",
            "entity_type": "Material",
            "canonical_name": "LFP",
            "aliases": ["lithium iron phosphate"],
        }
    ],
    "relations": [],
    "chunks_processed": 2,
    "extraction_model": "claude-haiku-4-5-20251001",
    "extracted_at": "2026-04-01T00:05:00Z",
}

_SAMPLE_WIKI_INDEX = (
    "# Wiki Index\n\n"
    "Materials: see `materials/`.\n\n"
    "## Recent\n"
    "- material:lfp\n"
)

_SAMPLE_WIKI_LFP = (
    "# LFP\n\n"
    "<!-- auto-start: evidence -->\n"
    "| Source | Claim | Confidence | Extracted |\n"
    "|--------|-------|-----------|-----------|\n"
    "<!-- auto-end: evidence -->\n\n"
    "<!-- human-start: summary -->\n"
    "LFP is a popular cathode for long-cycle-life applications.\n"
    "<!-- human-end: summary -->\n"
)

_SAMPLE_NORMALIZATION_YAML = """\
material:lfp:
  canonical_name: LFP
  aliases:
    - lithium iron phosphate
    - LiFePO4
mechanism:sei:
  canonical_name: SEI
  aliases:
    - solid electrolyte interphase
"""


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_chroma_singleton() -> Generator[None, None, None]:
    """Ensure the Chroma collection singleton in corpus_io is reset between tests."""
    yield
    import llm_rag.mcp.corpus_io as _corpus_io_mod

    _corpus_io_mod._collection = None


@pytest.fixture()
def mini_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a deterministic mini-corpus under ``tmp_path`` and point Settings at it.

    Layout::

        tmp_path/
            raw/papers/sample-lfp-001.md            + .manifest.json
            raw/papers/pending-doc.md               + .manifest.json   (no extracted stage)
            retrieval/chunks/papers-sample-lfp-001.jsonl
            retrieval/metadata/papers-sample-lfp-001.json
            graph/exports/papers-sample-lfp-001.json
            graph/snapshots/latest.graphml          (3-node fixture)
            wiki/index.md
            wiki/materials/lfp.md
            config/page-templates/                  (copied from project)
            config/entity-normalization.yaml        (3-entry fixture)
    """
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    get_settings.cache_clear()

    # raw/
    papers_dir = tmp_path / "raw" / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "sample-lfp-001.md").write_text(_SAMPLE_DOC_TEXT)
    (papers_dir / "sample-lfp-001.manifest.json").write_text(json.dumps(_SAMPLE_MANIFEST, indent=2))
    (papers_dir / "pending-doc.md").write_text("Pending content.")
    (papers_dir / "pending-doc.manifest.json").write_text(
        json.dumps(_SAMPLE_PENDING_MANIFEST, indent=2)
    )

    # retrieval/
    chunks_dir = tmp_path / "retrieval" / "chunks"
    chunks_dir.mkdir(parents=True)
    chunks_path = chunks_dir / "papers-sample-lfp-001.jsonl"
    chunks_path.write_text("\n".join(json.dumps(c) for c in _SAMPLE_CHUNKS))

    metadata_dir = tmp_path / "retrieval" / "metadata"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "papers-sample-lfp-001.json").write_text(
        json.dumps(_SAMPLE_CHUNKS, indent=2)
    )

    # graph/exports/
    exports_dir = tmp_path / "graph" / "exports"
    exports_dir.mkdir(parents=True)
    (exports_dir / "papers-sample-lfp-001.json").write_text(json.dumps(_SAMPLE_EXPORT, indent=2))

    # graph/snapshots/latest.graphml — small 3-node graph
    snapshots_dir = tmp_path / "graph" / "snapshots"
    snapshots_dir.mkdir(parents=True)
    g: nx.MultiDiGraph = nx.MultiDiGraph()
    g.add_node("material:lfp", entity_type="Material", canonical_name="LFP")
    g.add_node("mechanism:sei", entity_type="FailureMechanism", canonical_name="SEI")
    g.add_node("project:alpha", entity_type="Project", canonical_name="Alpha")
    g.add_edge(
        "mechanism:sei", "material:lfp", key="rel-001", relation_type="AFFECTS", weight=1.0
    )
    g.add_edge(
        "material:lfp", "project:alpha", key="rel-002", relation_type="ASSOCIATED_WITH", weight=1.0
    )
    nx.write_graphml(g, str(snapshots_dir / "latest.graphml"))

    # wiki/
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "index.md").write_text(_SAMPLE_WIKI_INDEX)
    materials_dir = wiki_dir / "materials"
    materials_dir.mkdir()
    (materials_dir / "lfp.md").write_text(_SAMPLE_WIKI_LFP)

    # config/page-templates/ — copy from project so get_template returns real templates
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    src_templates = PROJECT_ROOT / "config" / "page-templates"
    if src_templates.exists():
        shutil.copytree(src_templates, config_dir / "page-templates")
    else:
        (config_dir / "page-templates").mkdir()
        (config_dir / "page-templates" / "_fallback.md").write_text("# {{ canonical_name }}\n")

    # config/entity-normalization.yaml
    (config_dir / "entity-normalization.yaml").write_text(_SAMPLE_NORMALIZATION_YAML)

    yield tmp_path

    get_settings.cache_clear()
