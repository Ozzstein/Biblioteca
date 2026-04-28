"""Integration tests: ResearchAgent ↔ SupervisorAgent scheduling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from llm_rag.research.coordinator import ResearchAgent
from llm_rag.supervisor.loop import (
    SchedulerState,
    SubagentResult,
    SupervisorAgent,
    _run_subagent_sync,
    build_research_agent,
    load_sources_config,
)


def _sources_config() -> dict:
    return {
        "research_topics": ["LFP degradation", "SEI formation"],
        "subagents": {
            "arxiv": {
                "enabled": True,
                "schedule": "interval:hours=12",
                "max_results_per_query": 20,
            },
            "semantic_scholar": {
                "enabled": True,
                "schedule": "interval:hours=24",
                "max_results_per_query": 15,
            },
            "pubmed": {
                "enabled": True,
                "schedule": "interval:hours=48",
                "max_results_per_query": 10,
            },
            "unpaywall": {
                "enabled": True,
                "schedule": "on-demand",
            },
            "google_scholar": {
                "enabled": False,
                "schedule": "interval:hours=24",
                "max_results_per_query": 10,
            },
        },
    }


def _make_agent(tmp_path: Path) -> SupervisorAgent:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return SupervisorAgent(raw_dir=raw_dir, interval_seconds=0)


# --- build_research_agent ---


def test_build_research_agent_creates_enabled_subagents() -> None:
    config = _sources_config()
    agent = build_research_agent(MagicMock(), config)
    assert isinstance(agent, ResearchAgent)
    # 3 enabled interval subagents + 1 enabled on-demand = 4 total
    # (google_scholar disabled)
    assert len(agent.subagents) == 4
    class_names = {type(s).__name__ for s in agent.subagents}
    assert "ArXivSubagent" in class_names
    assert "SemanticScholarSubagent" in class_names
    assert "PubMedSubagent" in class_names
    assert "UnpaywallSubagent" in class_names
    assert "GoogleScholarSubagent" not in class_names


def test_build_research_agent_passes_max_results() -> None:
    config = {
        "subagents": {
            "arxiv": {"enabled": True, "schedule": "interval:hours=12", "max_results_per_query": 5},
        }
    }
    agent = build_research_agent(MagicMock(), config)
    assert len(agent.subagents) == 1
    assert agent.subagents[0].max_results == 5


def test_build_research_agent_skips_unknown_subagent() -> None:
    config = {
        "subagents": {
            "unknown_source": {"enabled": True, "schedule": "interval:hours=12"},
        }
    }
    agent = build_research_agent(MagicMock(), config)
    assert len(agent.subagents) == 0


def test_build_research_agent_empty_config() -> None:
    agent = build_research_agent(MagicMock(), {})
    assert len(agent.subagents) == 0


# --- init_research ---


def test_init_research_from_provided_config(tmp_path: Path) -> None:
    supervisor = _make_agent(tmp_path)
    config = _sources_config()
    research = supervisor.init_research(sources_config=config)
    assert isinstance(research, ResearchAgent)
    assert supervisor._research_agent is research
    assert len(research.subagents) == 4


def test_init_research_loads_from_yaml(tmp_path: Path) -> None:
    supervisor = _make_agent(tmp_path)
    with patch(
        "llm_rag.supervisor.loop.load_sources_config",
        return_value=_sources_config(),
    ):
        research = supervisor.init_research()
    assert isinstance(research, ResearchAgent)


# --- start_scheduler per-subagent scheduling ---


def test_scheduler_creates_per_subagent_jobs(tmp_path: Path) -> None:
    supervisor = _make_agent(tmp_path)
    config = _sources_config()
    topics = config["research_topics"]

    with patch("llm_rag.supervisor.loop.BackgroundScheduler") as MockSched:
        mock_scheduler = MagicMock()
        MockSched.return_value = mock_scheduler

        supervisor.start_scheduler(topics=topics, sources_config=config)

        # 3 enabled subagents with interval schedules (not on-demand, not disabled)
        assert mock_scheduler.add_job.call_count == 3

        # Verify each job's source_name argument
        job_ids = {call.kwargs["id"] for call in mock_scheduler.add_job.call_args_list}
        assert job_ids == {"arxiv", "semantic_scholar", "pubmed"}

        mock_scheduler.start.assert_called_once()


def test_scheduler_passes_topics_to_each_job(tmp_path: Path) -> None:
    supervisor = _make_agent(tmp_path)
    config = _sources_config()
    topics = ["LFP degradation", "SEI formation"]

    with patch("llm_rag.supervisor.loop.BackgroundScheduler") as MockSched:
        mock_scheduler = MagicMock()
        MockSched.return_value = mock_scheduler

        supervisor.start_scheduler(topics=topics, sources_config=config)

        for call in mock_scheduler.add_job.call_args_list:
            args = call.kwargs.get("args") or call[1].get("args")
            # args = [topics, source_name, research_agent, scheduler_state]
            assert args[0] == topics


def test_scheduler_uses_provided_research_agent(tmp_path: Path) -> None:
    supervisor = _make_agent(tmp_path)
    config = _sources_config()
    mock_agent = MagicMock(spec=ResearchAgent)

    with patch("llm_rag.supervisor.loop.BackgroundScheduler") as MockSched:
        mock_scheduler = MagicMock()
        MockSched.return_value = mock_scheduler

        supervisor.start_scheduler(
            topics=["LFP"],
            sources_config=config,
            research_agent=mock_agent,
        )

    assert supervisor._research_agent is mock_agent


def test_scheduler_auto_creates_research_agent_if_none(tmp_path: Path) -> None:
    supervisor = _make_agent(tmp_path)
    config = _sources_config()

    with patch("llm_rag.supervisor.loop.BackgroundScheduler") as MockSched:
        MockSched.return_value = MagicMock()
        supervisor.start_scheduler(topics=["LFP"], sources_config=config)

    assert supervisor._research_agent is not None
    assert isinstance(supervisor._research_agent, ResearchAgent)


# --- SchedulerState tracking ---


def test_scheduler_state_records_results() -> None:
    state = SchedulerState()
    r = SubagentResult(
        source_name="arxiv",
        started_at="2026-04-24T10:00:00+00:00",
        finished_at="2026-04-24T10:01:00+00:00",
        files_written=3,
    )
    state.record(r)
    assert len(state.results) == 1
    assert state.last_run["arxiv"] == "2026-04-24T10:01:00+00:00"


def test_run_subagent_sync_tracks_success() -> None:
    state = SchedulerState()
    mock_agent = MagicMock(spec=ResearchAgent)
    # asyncio.run will call agent.run(), which returns a coroutine
    mock_paths = [Path("/tmp/a.pdf"), Path("/tmp/b.pdf")]

    with patch("llm_rag.supervisor.loop.asyncio") as mock_asyncio:
        mock_asyncio.run.return_value = mock_paths
        _run_subagent_sync(["LFP"], "arxiv", mock_agent, state)

    assert len(state.results) == 1
    assert state.results[0].source_name == "arxiv"
    assert state.results[0].files_written == 2
    assert state.results[0].error is None
    mock_asyncio.run.assert_called_once()


def test_run_subagent_sync_tracks_error() -> None:
    state = SchedulerState()
    mock_agent = MagicMock(spec=ResearchAgent)

    with patch("llm_rag.supervisor.loop.asyncio") as mock_asyncio:
        mock_asyncio.run.side_effect = RuntimeError("API rate limit")
        _run_subagent_sync(["LFP"], "pubmed", mock_agent, state)

    assert len(state.results) == 1
    assert state.results[0].source_name == "pubmed"
    assert state.results[0].error == "API rate limit"


# --- load_sources_config ---


def test_load_sources_config_reads_yaml(tmp_path: Path) -> None:
    mock_settings = MagicMock()
    mock_settings.root_dir = tmp_path
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "sources.yaml").write_text(
        "research_topics:\n  - test topic\nsubagents:\n  arxiv:\n    enabled: true\n"
    )
    result = load_sources_config(mock_settings)
    assert result["research_topics"] == ["test topic"]
    assert result["subagents"]["arxiv"]["enabled"] is True


def test_load_sources_config_missing_file(tmp_path: Path) -> None:
    mock_settings = MagicMock()
    mock_settings.root_dir = tmp_path
    # tmp_path doesn't have config/sources.yaml
    result = load_sources_config(mock_settings)
    assert result == {"research_topics": [], "subagents": {}}
