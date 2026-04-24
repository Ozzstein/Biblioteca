from __future__ import annotations

from pathlib import Path

from llm_rag.pipeline.manifest import (
    create_manifest,
    load_manifest,
    manifest_path,
    needs_processing,
    save_manifest,
    update_stage,
)
from llm_rag.schemas.provenance import ProcessingStage


def test_manifest_path_is_sibling(tmp_path: Path) -> None:
    source = tmp_path / "papers" / "doc.md"
    assert manifest_path(source) == source.parent / "doc.manifest.json"


def test_load_manifest_missing_returns_none(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    assert load_manifest(source) is None


def test_create_save_load_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("hello battery")
    m = create_manifest(source, doc_id="papers/doc", doc_type="paper", source_connector="manual")
    save_manifest(m)
    loaded = load_manifest(source)
    assert loaded is not None
    assert loaded.doc_id == "papers/doc"
    assert loaded.content_hash.startswith("sha256:")
    assert loaded.stages_completed == []


def test_update_stage_adds_stage(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    m = create_manifest(source, doc_id="x", doc_type="paper", source_connector="manual")
    m2 = update_stage(m, ProcessingStage.INGESTED)
    assert ProcessingStage.INGESTED in m2.stages_completed
    assert ProcessingStage.INGESTED not in m.stages_completed  # original unchanged


def test_update_stage_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    m = create_manifest(source, doc_id="x", doc_type="paper", source_connector="manual")
    m2 = update_stage(update_stage(m, ProcessingStage.INGESTED), ProcessingStage.INGESTED)
    assert m2.stages_completed.count(ProcessingStage.INGESTED) == 1


def test_needs_processing_no_manifest(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    assert needs_processing(source, ProcessingStage.INGESTED) is True


def test_needs_processing_stage_complete(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    m = create_manifest(source, doc_id="x", doc_type="paper", source_connector="manual")
    save_manifest(update_stage(m, ProcessingStage.INGESTED))
    assert needs_processing(source, ProcessingStage.INGESTED) is False


def test_needs_processing_hash_changed(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("original")
    m = create_manifest(source, doc_id="x", doc_type="paper", source_connector="manual")
    save_manifest(update_stage(m, ProcessingStage.INGESTED))
    source.write_text("changed content")
    assert needs_processing(source, ProcessingStage.INGESTED) is True
