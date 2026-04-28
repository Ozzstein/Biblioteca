from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_rag.mcp.corpus_io import (
    get_chunks,
    get_export,
    get_manifest,
    ingest_file,
    list_pending_docs,
    save_export,
    save_manifest,
)


@pytest.fixture(autouse=True)
def reset_chroma_singleton() -> Generator[None, None, None]:
    yield
    import llm_rag.mcp.corpus_io as _corpus_io_mod
    _corpus_io_mod._collection = None


@pytest.fixture()
def raw_dir(tmp_path: Path) -> Path:
    d = tmp_path / "raw" / "papers"
    d.mkdir(parents=True)
    return tmp_path / "raw"


@pytest.fixture()
def chunks_dir(tmp_path: Path) -> Path:
    d = tmp_path / "retrieval" / "chunks"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def exports_dir(tmp_path: Path) -> Path:
    d = tmp_path / "graph" / "exports"
    d.mkdir(parents=True)
    return d


async def test_get_chunks_returns_empty_for_missing_doc(chunks_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(chunks_dir.parent.parent))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await get_chunks("papers/no-such-doc")
    assert result == []
    get_settings.cache_clear()


async def test_get_chunks_reads_jsonl(chunks_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (chunks_dir / "papers-sample.jsonl").write_text(
        json.dumps({"text": "hello", "chunk_index": 0}) + "\n"
        + json.dumps({"text": "world", "chunk_index": 1}) + "\n"
    )
    result = await get_chunks("papers/sample")
    assert len(result) == 2
    assert result[0]["text"] == "hello"
    get_settings.cache_clear()


async def test_get_manifest_returns_none_for_missing(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result = await get_manifest("papers/no-such-doc")
    assert result is None
    get_settings.cache_clear()


async def test_get_manifest_finds_by_doc_id(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    manifest_data = {"doc_id": "papers/lfp-001", "source_path": "raw/papers/lfp-001.md",
                     "content_hash": "sha256:abc", "doc_type": "paper",
                     "source_connector": "arxiv", "fetched_at": "2026-01-01T00:00:00Z",
                     "last_processed": "2026-01-01T00:00:00Z", "stages_completed": [],
                     "error": None, "title": None, "authors": [], "doi": None, "arxiv_id": None}
    (raw_dir / "papers" / "lfp-001.manifest.json").write_text(json.dumps(manifest_data))
    result = await get_manifest("papers/lfp-001")
    assert result is not None
    assert result["doc_id"] == "papers/lfp-001"
    get_settings.cache_clear()


async def test_save_manifest_writes_sidecar(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    source = raw_dir / "papers" / "lfp-001.md"
    source.write_text("content")
    manifest_data = {"doc_id": "papers/lfp-001", "source_path": str(source),
                     "content_hash": "sha256:abc", "doc_type": "paper",
                     "source_connector": "arxiv", "fetched_at": "2026-01-01T00:00:00Z",
                     "last_processed": "2026-01-01T00:00:00Z", "stages_completed": [],
                     "error": None, "title": None, "authors": [], "doi": None, "arxiv_id": None}
    await save_manifest(manifest_data)
    sidecar = raw_dir / "papers" / "lfp-001.manifest.json"
    assert sidecar.exists()
    saved = json.loads(sidecar.read_text())
    assert saved["doc_id"] == "papers/lfp-001"
    get_settings.cache_clear()


async def test_save_export_writes_json(exports_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    result_data = {
        "doc_id": "papers/lfp-001",
        "entities": [],
        "relations": [],
        "chunks_processed": 0,
        "extraction_model": "claude-haiku-4-5-20251001",
        "extracted_at": "2026-01-01T00:00:00Z",
    }
    await save_export(result_data)
    out = exports_dir / "papers-lfp-001.json"
    assert out.exists()
    assert json.loads(out.read_text())["doc_id"] == "papers/lfp-001"
    get_settings.cache_clear()


async def test_list_pending_docs_finds_missing_stage(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    manifest_data = {"doc_id": "papers/lfp-001", "source_path": "raw/papers/lfp-001.md",
                     "content_hash": "sha256:abc", "doc_type": "paper",
                     "source_connector": "arxiv", "fetched_at": "2026-01-01T00:00:00Z",
                     "last_processed": "2026-01-01T00:00:00Z", "stages_completed": ["ingested"],
                     "error": None, "title": None, "authors": [], "doi": None, "arxiv_id": None}
    (raw_dir / "papers" / "lfp-001.manifest.json").write_text(json.dumps(manifest_data))
    result = await list_pending_docs("extracted")
    assert "papers/lfp-001" in result
    get_settings.cache_clear()


async def test_get_export_returns_dict_when_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    exports = tmp_path / "graph" / "exports"
    exports.mkdir(parents=True)
    data = {"doc_id": "papers/test-001", "entities": []}
    (exports / "papers-test-001.json").write_text(json.dumps(data))
    result = await get_export("papers/test-001")
    assert result == data
    get_settings.cache_clear()


async def test_get_export_returns_none_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (tmp_path / "graph" / "exports").mkdir(parents=True)
    result = await get_export("papers/no-such-doc")
    assert result is None
    get_settings.cache_clear()


async def test_ingest_file_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    # Create source file
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    source = raw / "test-paper.md"
    source.write_text("# Test Paper\n\nThis is test content about LFP batteries.")
    # Create retrieval dirs
    (tmp_path / "retrieval" / "chunks").mkdir(parents=True)
    (tmp_path / "retrieval" / "metadata").mkdir(parents=True)
    # Mock Chroma collection
    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": []}
    monkeypatch.setattr("llm_rag.mcp.corpus_io._get_collection", lambda: mock_collection)
    result = await ingest_file(
        source_path=str(source),
        doc_id="papers/test-paper",
        doc_type="paper",
        source_connector="manual",
    )
    assert result["doc_id"] == "papers/test-paper"
    assert "ingested" in result["stages_completed"]
    chunks_file = tmp_path / "retrieval" / "chunks" / "papers-test-paper.jsonl"
    assert chunks_file.exists()
    mock_collection.add.assert_called_once()
    get_settings.cache_clear()


async def test_ingest_file_refreshes_content_hash_on_reingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """content_hash in the manifest must reflect the *current* file after reingest.

    Without the fix, the hash stored after the first ingest is never updated on
    the second call, so needs_processing() would detect a mismatch every time
    and loop forever.
    """
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    from llm_rag.utils.hashing import content_hash
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    source = raw / "test-paper.md"
    source.write_text("# Version 1\n\nOriginal content.")
    (tmp_path / "retrieval" / "chunks").mkdir(parents=True)
    (tmp_path / "retrieval" / "metadata").mkdir(parents=True)
    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": []}
    monkeypatch.setattr("llm_rag.mcp.corpus_io._get_collection", lambda: mock_collection)

    # First ingest
    result1 = await ingest_file(str(source), "papers/test-paper", "papers", "manual")
    hash_after_first_ingest = result1["content_hash"]
    assert hash_after_first_ingest == content_hash(source)

    # Simulate file change
    source.write_text("# Version 2\n\nUpdated content — file has changed.")
    expected_new_hash = content_hash(source)
    assert expected_new_hash != hash_after_first_ingest, "test setup: hashes must differ"

    # Reingest — hash must be refreshed
    result2 = await ingest_file(str(source), "papers/test-paper", "papers", "manual")
    assert result2["content_hash"] == expected_new_hash, (
        "content_hash was not updated on reingest; needs_processing() would loop forever"
    )
    # Verify the manifest on disk also has the new hash
    manifest_file = raw / "test-paper.manifest.json"
    saved = json.loads(manifest_file.read_text())
    assert saved["content_hash"] == expected_new_hash
    get_settings.cache_clear()


async def test_ingest_file_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    source = raw / "test-paper.md"
    source.write_text("# Test Paper\n\nContent about batteries.")
    (tmp_path / "retrieval" / "chunks").mkdir(parents=True)
    (tmp_path / "retrieval" / "metadata").mkdir(parents=True)
    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": []}
    monkeypatch.setattr("llm_rag.mcp.corpus_io._get_collection", lambda: mock_collection)
    await ingest_file(str(source), "papers/test-paper", "papers", "manual")
    await ingest_file(str(source), "papers/test-paper", "papers", "manual")
    # delete+re-add on second run — so add is called twice total
    assert mock_collection.add.call_count == 2
    get_settings.cache_clear()


async def test_scan_pending_files_finds_unprocessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    (raw / "doc.md").write_text("content")
    from llm_rag.mcp.corpus_io import scan_pending_files
    result = await scan_pending_files()
    assert str(raw / "doc.md") in result["pending_paths"]
    get_settings.cache_clear()


async def test_scan_pending_files_skips_fully_processed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    doc = raw / "done.md"
    doc.write_text("content")
    from llm_rag.pipeline.manifest import create_manifest, update_stage
    from llm_rag.pipeline.manifest import save_manifest as _save
    from llm_rag.schemas.provenance import ProcessingStage
    manifest = create_manifest(doc, "papers/done", "papers", "manual")
    for stage in ProcessingStage:
        manifest = update_stage(manifest, stage)
    _save(manifest)
    from llm_rag.mcp.corpus_io import scan_pending_files
    result = await scan_pending_files()
    assert str(doc) not in result["pending_paths"]
    get_settings.cache_clear()


async def test_scan_pending_files_skips_manifest_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    (raw / "doc.manifest.json").write_text("{}")
    from llm_rag.mcp.corpus_io import scan_pending_files
    result = await scan_pending_files()
    assert result["pending_paths"] == []
    get_settings.cache_clear()


async def test_search_chunks_returns_matching_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["LFP shows 170 mAh/g capacity."]],
        "metadatas": [
            [{"doc_id": "papers/lfp-001", "chunk_index": 2, "section": "results"}]
        ],
    }
    monkeypatch.setattr("llm_rag.mcp.corpus_io._get_collection", lambda: mock_collection)
    from llm_rag.mcp.corpus_io import search_chunks
    result = await search_chunks("LFP capacity")
    assert len(result) == 1
    assert result[0]["text"] == "LFP shows 170 mAh/g capacity."
    assert result[0]["doc_id"] == "papers/lfp-001"
    assert result[0]["chunk_index"] == 2
    assert result[0]["section"] == "results"
    mock_collection.query.assert_called_once_with(
        query_texts=["LFP capacity"],
        n_results=5,
        include=["documents", "metadatas"],
    )
    get_settings.cache_clear()


async def test_search_chunks_empty_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [[]],
        "metadatas": [[]],
    }
    monkeypatch.setattr("llm_rag.mcp.corpus_io._get_collection", lambda: mock_collection)
    from llm_rag.mcp.corpus_io import search_chunks
    result = await search_chunks("LFP capacity")
    assert result == []
    get_settings.cache_clear()
