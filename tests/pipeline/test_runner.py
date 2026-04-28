from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from llm_rag.config import get_settings
from llm_rag.pipeline.manifest import create_manifest, save_manifest, update_stage
from llm_rag.pipeline.runner import PipelineRunner
from llm_rag.schemas.provenance import ProcessingStage


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture()
def source_file(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "test-paper.md"
    source.write_text("LFP shows excellent cycle life.")
    return source


async def test_runner_runs_all_five_stages_for_new_doc(settings: object, source_file: Path) -> None:
    with patch("llm_rag.pipeline.runner.MCPPool") as MockPool:
        mock_pool = AsyncMock()
        mock_pool.__aenter__.return_value = mock_pool
        mock_pool.__aexit__ = AsyncMock(return_value=False)
        MockPool.return_value = mock_pool
        # Return valid JSON for each stage (keyed by agent definition name)
        stage_responses = {
            "ingestion": '{"doc_id": "test", "source_path": "/test.md", "doc_type": "paper", "content_hash": "abc", "ingested_at": "2026-04-24T00:00:00"}',
            "extraction-paper": '[{"entity_id": "e1", "name": "LFP", "entity_type": "Material", "aliases": [], "source_chunks": [], "confidence": 0.9}]',
            "normalization": '[{"entity_id": "e1", "name": "LFP", "entity_type": "Material", "aliases": [], "source_chunks": [], "confidence": 0.9}]',
            "wiki_compiler": '{"entity_id": "e1", "title": "LFP", "sections": {}, "auto_sections": [], "human_sections": []}',
            "graph_curator": '{"add_nodes": [], "add_edges": [], "remove_nodes": [], "remove_edges": []}',
        }
        with patch("llm_rag.pipeline.runner.run_agent", new=AsyncMock(side_effect=lambda *args, **kwargs: stage_responses[args[0].name])) as mock_run:
            async with PipelineRunner(settings=settings) as runner:  # type: ignore[call-arg]
                await runner.run(source_file)
    assert mock_run.call_count == 5


async def test_runner_skips_completed_stages(settings: object, source_file: Path, tmp_path: Path) -> None:
    manifest = create_manifest(source_file, "papers/test-paper", "papers", "manual")
    manifest = update_stage(manifest, ProcessingStage.INGESTED)
    manifest = update_stage(manifest, ProcessingStage.EXTRACTED)
    save_manifest(manifest)
    with patch("llm_rag.pipeline.runner.MCPPool") as MockPool:
        mock_pool = AsyncMock()
        mock_pool.__aenter__.return_value = mock_pool
        mock_pool.__aexit__ = AsyncMock(return_value=False)
        MockPool.return_value = mock_pool
        # Return valid JSON for remaining stages
        stage_responses = {
            "normalization": '[{"entity_id": "e1", "name": "LFP", "entity_type": "Material", "aliases": [], "source_chunks": [], "confidence": 0.9}]',
            "wiki_compiler": '{"entity_id": "e1", "title": "LFP", "sections": {}, "auto_sections": [], "human_sections": []}',
            "graph_curator": '{"add_nodes": [], "add_edges": [], "remove_nodes": [], "remove_edges": []}',
        }
        with patch("llm_rag.pipeline.runner.run_agent", new=AsyncMock(side_effect=lambda *args, **kwargs: stage_responses[args[0].name])) as mock_run:
            async with PipelineRunner(settings=settings) as runner:  # type: ignore[call-arg]
                await runner.run(source_file)
    # NORMALIZED, WIKI_COMPILED, GRAPH_UPDATED — three stages remain
    assert mock_run.call_count == 3


async def test_runner_force_runs_all_stages(settings: object, source_file: Path, tmp_path: Path) -> None:
    manifest = create_manifest(source_file, "papers/test-paper", "papers", "manual")
    for stage in ProcessingStage:
        manifest = update_stage(manifest, stage)
    save_manifest(manifest)
    with patch("llm_rag.pipeline.runner.MCPPool") as MockPool:
        mock_pool = AsyncMock()
        mock_pool.__aenter__.return_value = mock_pool
        mock_pool.__aexit__ = AsyncMock(return_value=False)
        MockPool.return_value = mock_pool
        # Return valid JSON for each stage
        stage_responses = {
            "ingestion": '{"doc_id": "test", "source_path": "/test.md", "doc_type": "paper", "content_hash": "abc", "ingested_at": "2026-04-24T00:00:00"}',
            "extraction-paper": '[{"entity_id": "e1", "name": "LFP", "entity_type": "Material", "aliases": [], "source_chunks": [], "confidence": 0.9}]',
            "normalization": '[{"entity_id": "e1", "name": "LFP", "entity_type": "Material", "aliases": [], "source_chunks": [], "confidence": 0.9}]',
            "wiki_compiler": '{"entity_id": "e1", "title": "LFP", "sections": {}, "auto_sections": [], "human_sections": []}',
            "graph_curator": '{"add_nodes": [], "add_edges": [], "remove_nodes": [], "remove_edges": []}',
        }
        with patch("llm_rag.pipeline.runner.run_agent", new=AsyncMock(side_effect=lambda *args, **kwargs: stage_responses[args[0].name])) as mock_run:
            async with PipelineRunner(settings=settings) as runner:  # type: ignore[call-arg]
                await runner.run(source_file, force=True)
    assert mock_run.call_count == 5


async def test_runner_context_manager_enters_pool(settings: object) -> None:
    with patch("llm_rag.pipeline.runner.MCPPool") as MockPool:
        mock_pool = AsyncMock()
        mock_pool.__aenter__.return_value = mock_pool
        mock_pool.__aexit__ = AsyncMock(return_value=False)
        MockPool.return_value = mock_pool
        async with PipelineRunner(settings=settings) as runner:  # type: ignore[call-arg]
            assert runner._pool is mock_pool
    mock_pool.__aexit__.assert_called_once()
