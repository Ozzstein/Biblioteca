from __future__ import annotations

import json
import queue
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.supervisor.loop import SupervisorAgent, _parse_schedule


def _make_agent(tmp_path: Path, **kwargs: object) -> SupervisorAgent:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return SupervisorAgent(raw_dir=raw_dir, interval_seconds=0, **kwargs)


def _write_doc(raw_dir: Path, name: str = "paper.md") -> Path:
    sub = raw_dir / "papers"
    sub.mkdir(parents=True, exist_ok=True)
    doc = sub / name
    doc.write_text("LFP content")
    return doc


async def test_run_cycle_calls_scan_and_gather(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    doc = _write_doc(agent.raw_dir)

    mock_result = MagicMock()
    mock_result.isError = False
    mock_result.content = [MagicMock(text=json.dumps({"pending_paths": [str(doc)]}))]

    mock_session = MagicMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)

    mock_pool = MagicMock()
    mock_pool.get.return_value = mock_session
    agent._pool = mock_pool

    mock_runner = AsyncMock()
    mock_runner.__aenter__ = AsyncMock(return_value=mock_runner)
    mock_runner.__aexit__ = AsyncMock(return_value=None)

    with patch("llm_rag.supervisor.loop.PipelineRunner", return_value=mock_runner):
        with patch.object(agent, "_run_reviewer", new=AsyncMock()):
            await agent._run_cycle()

    mock_runner.run.assert_called_once_with(doc)


async def test_run_cycle_drains_file_queue(tmp_path: Path) -> None:
    q: queue.Queue[Path] = queue.Queue()
    extra = tmp_path / "extra.md"
    extra.write_text("content")
    q.put(extra)

    agent = _make_agent(tmp_path, file_queue=q)

    mock_result = MagicMock()
    mock_result.isError = False
    mock_result.content = [MagicMock(text=json.dumps({"pending_paths": []}))]

    mock_session = MagicMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)

    mock_pool = MagicMock()
    mock_pool.get.return_value = mock_session
    agent._pool = mock_pool

    mock_runner = AsyncMock()
    mock_runner.__aenter__ = AsyncMock(return_value=mock_runner)
    mock_runner.__aexit__ = AsyncMock(return_value=None)

    with patch("llm_rag.supervisor.loop.PipelineRunner", return_value=mock_runner):
        with patch.object(agent, "_run_reviewer", new=AsyncMock()):
            await agent._run_cycle()

    mock_runner.run.assert_called_once_with(extra)
    assert q.empty()


async def test_run_cycle_empty_skips_runner(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)

    mock_result = MagicMock()
    mock_result.isError = False
    mock_result.content = [MagicMock(text=json.dumps({"pending_paths": []}))]

    mock_session = MagicMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)

    mock_pool = MagicMock()
    mock_pool.get.return_value = mock_session
    agent._pool = mock_pool

    with patch("llm_rag.supervisor.loop.PipelineRunner") as MockRunner:
        await agent._run_cycle()

    MockRunner.assert_not_called()


async def test_run_iterates_max_iterations(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    cycle_calls: list[None] = []

    async def fake_cycle() -> None:
        cycle_calls.append(None)

    mock_pool = MagicMock()
    mock_pool.__aenter__ = AsyncMock(return_value=mock_pool)
    mock_pool.__aexit__ = AsyncMock(return_value=None)

    with patch.object(agent, "_run_cycle", new=fake_cycle):
        with patch("llm_rag.supervisor.loop.MCPPool", return_value=mock_pool):
            await agent.run(max_iterations=2)

    assert len(cycle_calls) == 2


def test_parse_schedule_interval_hours() -> None:
    result = _parse_schedule("interval:hours=12")
    assert result == {"hours": 12}


def test_parse_schedule_on_demand_returns_none() -> None:
    assert _parse_schedule("on-demand") is None


def test_parse_schedule_interval_multi_param() -> None:
    result = _parse_schedule("interval:hours=24,minutes=30")
    assert result == {"hours": 24, "minutes": 30}


def test_start_scheduler_registers_enabled_jobs(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    sources_config = {
        "subagents": {
            "arxiv": {"enabled": True, "schedule": "interval:hours=12"},
            "pubmed": {"enabled": True, "schedule": "interval:hours=48"},
            "google_scholar": {"enabled": False, "schedule": "interval:hours=24"},
        }
    }
    mock_research = MagicMock()
    with patch("llm_rag.supervisor.loop.BackgroundScheduler") as MockSched:
        mock_scheduler = MagicMock()
        MockSched.return_value = mock_scheduler
        agent.start_scheduler(
            topics=["LFP degradation"],
            sources_config=sources_config,
            research_agent=mock_research,
        )
        assert mock_scheduler.add_job.call_count == 2
        mock_scheduler.start.assert_called_once()


def test_stop_scheduler_shuts_down(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    with patch("llm_rag.supervisor.loop.BackgroundScheduler") as MockSched:
        mock_scheduler = MagicMock()
        MockSched.return_value = mock_scheduler
        agent.start_scheduler(
            topics=[],
            sources_config={"subagents": {}},
            research_agent=MagicMock(),
        )
        agent.stop_scheduler()
        mock_scheduler.shutdown.assert_called_once_with(wait=False)
        assert agent._scheduler is None
