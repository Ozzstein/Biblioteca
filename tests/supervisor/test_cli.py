"""Tests for supervisor CLI commands."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from llm_rag.cli import app
from llm_rag.supervisor.state import SupervisorState, save_pid, save_state

runner = CliRunner()


def test_supervisor_help():
    result = runner.invoke(app, ["supervisor", "--help"])
    assert result.exit_code == 0
    assert "supervisor" in result.output.lower()


def test_supervisor_status_not_running(tmp_path: Path):
    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = MagicMock()
        s.root_dir = tmp_path
        mock_settings.return_value = s
        result = runner.invoke(app, ["supervisor", "status"])

    assert result.exit_code == 0
    assert "Running:" in result.output
    assert "no" in result.output


def test_supervisor_status_with_state(tmp_path: Path):
    # Set up state files
    sup_dir = tmp_path / ".supervisor"
    sup_dir.mkdir(parents=True)
    state_file = sup_dir / "state.json"
    pid_file = sup_dir / "supervisor.pid"

    state = SupervisorState(
        pid=os.getpid(),
        start_time="2026-04-24T10:00:00+00:00",
        last_heartbeat="2026-04-24T10:05:00+00:00",
        files_processed=7,
        errors=2,
    )
    save_state(state, state_file)
    save_pid(os.getpid(), pid_file)

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = MagicMock()
        s.root_dir = tmp_path
        mock_settings.return_value = s
        result = runner.invoke(app, ["supervisor", "status"])

    assert result.exit_code == 0
    assert "yes" in result.output
    assert "Files processed:" in result.output
    assert "7" in result.output
    assert "Errors:" in result.output
    assert "2" in result.output


def test_supervisor_stop_not_running(tmp_path: Path):
    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = MagicMock()
        s.root_dir = tmp_path
        mock_settings.return_value = s
        result = runner.invoke(app, ["supervisor", "stop"])

    assert result.exit_code == 1
    assert "not running" in result.output.lower()


def test_supervisor_stop_sends_signal(tmp_path: Path):
    sup_dir = tmp_path / ".supervisor"
    sup_dir.mkdir(parents=True)
    pid_file = sup_dir / "supervisor.pid"
    save_pid(os.getpid(), pid_file)

    with (
        patch("llm_rag.cli.get_settings") as mock_settings,
        patch("llm_rag.supervisor.state.os.kill") as mock_kill,
    ):
        s = MagicMock()
        s.root_dir = tmp_path
        mock_settings.return_value = s
        # First os.kill(pid, 0) for is_running, then os.kill(pid, SIGTERM) for stop
        mock_kill.return_value = None
        result = runner.invoke(app, ["supervisor", "stop"])

    assert result.exit_code == 0
    assert "stop signal" in result.output.lower()


def test_supervisor_start_already_running(tmp_path: Path):
    sup_dir = tmp_path / ".supervisor"
    sup_dir.mkdir(parents=True)
    pid_file = sup_dir / "supervisor.pid"
    save_pid(os.getpid(), pid_file)

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = MagicMock()
        s.root_dir = tmp_path
        s.config_dir = tmp_path / "config"
        mock_settings.return_value = s
        result = runner.invoke(app, ["supervisor", "start"])

    assert result.exit_code == 1
    assert "already running" in result.output.lower()


def test_supervisor_start_foreground_with_immediate_shutdown(tmp_path: Path):
    """Start in foreground mode; _run_cycle raises to break the loop."""
    sup_dir = tmp_path / ".supervisor"
    sup_dir.mkdir(parents=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    inbox = tmp_path / "raw" / "inbox"
    inbox.mkdir(parents=True)

    with (
        patch("llm_rag.cli.get_settings") as mock_settings,
        patch("llm_rag.supervisor.loop.SupervisorAgent._run_cycle", side_effect=KeyboardInterrupt),
        patch("llm_rag.supervisor.watcher.InboxWatcher.start"),
        patch("llm_rag.supervisor.watcher.InboxWatcher.stop"),
        patch("llm_rag.supervisor.loop.MCPPool"),
    ):
        s = MagicMock()
        s.root_dir = tmp_path
        s.config_dir = config_dir
        s.raw_dir = tmp_path / "raw"
        s.model_contradiction = "claude-haiku-4-5-20251001"
        mock_settings.return_value = s
        result = runner.invoke(app, ["supervisor", "start", "--foreground"])

    # KeyboardInterrupt triggers the finally block for cleanup
    assert "Supervisor started in foreground" in result.output


def test_supervisor_status_no_state_file(tmp_path: Path):
    sup_dir = tmp_path / ".supervisor"
    sup_dir.mkdir(parents=True)

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = MagicMock()
        s.root_dir = tmp_path
        mock_settings.return_value = s
        result = runner.invoke(app, ["supervisor", "status"])

    assert result.exit_code == 0
    assert "No state file found" in result.output
