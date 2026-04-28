from __future__ import annotations

from llm_rag.config import get_settings
from llm_rag.pipeline.runner import PipelineRunner
from llm_rag.schemas.provenance import DocType


def test_agent_models_match_settings() -> None:
    settings = get_settings()
    runner = PipelineRunner(settings=settings)
    assert runner._ingestion.model == settings.model_bulk_extraction
    assert runner._extraction.model == settings.model_bulk_extraction
    assert runner._normalization.model == settings.model_bulk_extraction
    assert runner._wiki_compiler.model == settings.model_wiki_compilation
    assert runner._graph_curator.model == settings.model_bulk_extraction


def test_agent_mcp_servers_are_correct() -> None:
    settings = get_settings()
    runner = PipelineRunner(settings=settings)
    assert runner._ingestion.mcp_servers == ["corpus-io"]
    assert runner._extraction.mcp_servers == ["corpus-io"]
    assert set(runner._normalization.mcp_servers) == {"corpus-io", "graph-io"}
    assert set(runner._wiki_compiler.mcp_servers) == {"corpus-io", "wiki-io"}
    assert set(runner._graph_curator.mcp_servers) == {"corpus-io", "graph-io"}


def test_all_prompt_files_exist() -> None:
    settings = get_settings()
    runner = PipelineRunner(settings=settings)
    for defn in [
        runner._ingestion,
        runner._extraction,
        runner._normalization,
        runner._wiki_compiler,
        runner._graph_curator,
    ]:
        prompt_file = defn.prompt_path(settings)
        assert prompt_file.exists(), f"Missing prompt file: {prompt_file}"


def test_extraction_prompt_selection_by_doc_type() -> None:
    settings = get_settings()
    runner = PipelineRunner(settings=settings)
    assert runner._select_extraction_agent(DocType.PAPER).name == "extraction-paper"
    assert runner._select_extraction_agent(DocType.SOP).name == "extraction-sop"
    assert runner._select_extraction_agent(DocType.MEETING).name == "extraction-meeting"
    assert runner._select_extraction_agent(DocType.REPORT).name == "extraction-report"
    assert runner._select_extraction_agent(DocType.UNKNOWN).name == "extraction-paper"
