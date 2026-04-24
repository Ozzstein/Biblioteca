from pathlib import Path

from llm_rag.config import Settings, get_settings


def test_settings_returns_settings_instance():
    s = get_settings()
    assert isinstance(s, Settings)


def test_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_default_model_assignments():
    s = get_settings()
    assert s.model_bulk_extraction == "claude-haiku-4-5-20251001"
    assert s.model_wiki_compilation == "claude-sonnet-4-6"
    assert s.model_deep_analysis == "claude-opus-4-7"


def test_default_pipeline_settings():
    s = get_settings()
    assert s.chunk_size == 512
    assert s.chunk_overlap == 64
    assert s.relevance_threshold == 0.6


def test_paths_are_path_objects():
    s = get_settings()
    assert isinstance(s.raw_dir, Path)
    assert isinstance(s.wiki_dir, Path)
    assert isinstance(s.graph_dir, Path)


def test_raw_dir_ends_with_raw():
    s = get_settings()
    assert s.raw_dir.name == "raw"


def test_missing_api_key_defaults_to_empty_string():
    s = get_settings()
    assert isinstance(s.anthropic_api_key, str)
