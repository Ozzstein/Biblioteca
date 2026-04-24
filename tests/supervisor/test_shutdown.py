"""Tests for graceful shutdown handling."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.supervisor.shutdown import ShutdownManager, ShutdownReason
from llm_rag.supervisor.state import SupervisorState, save_state


class TestShutdownManager:
    """Tests for the ShutdownManager class."""

    def test_initial_state(self):
        mgr = ShutdownManager()
        assert mgr.is_shutting_down is False
        assert mgr.reason is None

    def test_request_shutdown_sets_flag(self):
        mgr = ShutdownManager()
        mgr.request_shutdown(ShutdownReason.SIGTERM)
        assert mgr.is_shutting_down is True
        assert mgr.reason == ShutdownReason.SIGTERM

    def test_request_shutdown_idempotent(self):
        """Second call doesn't overwrite reason."""
        mgr = ShutdownManager()
        mgr.request_shutdown(ShutdownReason.SIGTERM)
        mgr.request_shutdown(ShutdownReason.SIGINT)
        assert mgr.reason == ShutdownReason.SIGTERM

    def test_threading_event_set_on_shutdown(self):
        mgr = ShutdownManager()
        assert not mgr.shutdown_event.is_set()
        mgr.request_shutdown(ShutdownReason.MANUAL)
        assert mgr.shutdown_event.is_set()

    def test_async_event_set_on_shutdown(self):
        mgr = ShutdownManager()
        evt = mgr.get_async_event()
        assert not evt.is_set()
        mgr.request_shutdown(ShutdownReason.SIGINT)
        assert evt.is_set()

    def test_handle_sigterm(self):
        mgr = ShutdownManager()
        mgr._handle_signal(signal.SIGTERM, None)
        assert mgr.is_shutting_down is True
        assert mgr.reason == ShutdownReason.SIGTERM

    def test_handle_sigint(self):
        mgr = ShutdownManager()
        mgr._handle_signal(signal.SIGINT, None)
        assert mgr.is_shutting_down is True
        assert mgr.reason == ShutdownReason.SIGINT

    def test_handle_sighup(self):
        mgr = ShutdownManager()
        mgr._handle_signal(signal.SIGHUP, None)
        assert mgr.is_shutting_down is True
        assert mgr.reason == ShutdownReason.SIGHUP

    def test_register_and_unregister_signals(self):
        mgr = ShutdownManager()
        # Save originals
        orig_term = signal.getsignal(signal.SIGTERM)
        orig_int = signal.getsignal(signal.SIGINT)

        mgr.register_signals()
        # Handlers should now be mgr._handle_signal
        assert signal.getsignal(signal.SIGTERM) == mgr._handle_signal
        assert signal.getsignal(signal.SIGINT) == mgr._handle_signal
        assert signal.getsignal(signal.SIGHUP) == mgr._handle_signal

        mgr.unregister_signals()
        # Originals restored
        assert signal.getsignal(signal.SIGTERM) == orig_term
        assert signal.getsignal(signal.SIGINT) == orig_int


class TestSupervisorGracefulShutdown:
    """Tests for SupervisorAgent.graceful_shutdown()."""

    def _make_supervisor(self, tmp_path: Path, shutdown_mgr: ShutdownManager | None = None):
        """Create a SupervisorAgent with minimal dependencies."""
        from llm_rag.supervisor.loop import SupervisorAgent

        state_file = tmp_path / "state.json"
        pid_file = tmp_path / "supervisor.pid"
        pid_file.write_text("12345")

        state = SupervisorState(
            pid=12345,
            start_time="2026-04-24T00:00:00+00:00",
            last_heartbeat="2026-04-24T00:00:00+00:00",
            files_processed=5,
            errors=1,
        )
        save_state(state, state_file)

        mgr = shutdown_mgr or ShutdownManager()

        with patch("llm_rag.supervisor.loop.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                root_dir=tmp_path,
                raw_dir=tmp_path / "raw",
                model_contradiction="claude-haiku-4-5-20251001",
            )
            sup = SupervisorAgent(
                raw_dir=tmp_path / "raw",
                settings=mock_settings.return_value,
                supervisor_state=state,
                state_file=state_file,
                shutdown_manager=mgr,
                pid_file=pid_file,
            )
        return sup, state, state_file, pid_file

    @pytest.mark.asyncio
    async def test_graceful_shutdown_clears_pid(self, tmp_path):
        sup, state, state_file, pid_file = self._make_supervisor(tmp_path)
        assert pid_file.exists()

        await sup.graceful_shutdown(ShutdownReason.SIGTERM)

        assert not pid_file.exists()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_saves_state(self, tmp_path):
        sup, state, state_file, pid_file = self._make_supervisor(tmp_path)

        await sup.graceful_shutdown(ShutdownReason.SIGINT)

        # State file should still exist with updated heartbeat
        assert state_file.exists()
        from llm_rag.supervisor.state import load_state

        saved = load_state(state_file)
        assert saved is not None
        assert saved.files_processed == 5
        assert saved.errors == 1

    @pytest.mark.asyncio
    async def test_graceful_shutdown_stops_scheduler(self, tmp_path):
        sup, state, state_file, pid_file = self._make_supervisor(tmp_path)
        mock_scheduler = MagicMock()
        sup._scheduler = mock_scheduler

        await sup.graceful_shutdown(ShutdownReason.SIGTERM)

        mock_scheduler.shutdown.assert_called_once_with(wait=False)

    @pytest.mark.asyncio
    async def test_run_cycle_skips_when_shutting_down(self, tmp_path):
        mgr = ShutdownManager()
        mgr.request_shutdown(ShutdownReason.SIGTERM)

        sup, state, state_file, pid_file = self._make_supervisor(tmp_path, shutdown_mgr=mgr)
        sup._pool = MagicMock()

        # _run_cycle should return early without calling scan_pending_files
        await sup._run_cycle()
        sup._pool.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_loop_exits_on_shutdown(self, tmp_path):
        mgr = ShutdownManager()
        sup, state, state_file, pid_file = self._make_supervisor(tmp_path, shutdown_mgr=mgr)

        # Request shutdown after the first iteration starts
        async def shutdown_after_delay():
            await asyncio.sleep(0.05)
            mgr.request_shutdown(ShutdownReason.SIGINT)

        # Mock run to avoid MCP pool issues
        cycle_count = 0

        async def mock_run_cycle():
            nonlocal cycle_count
            cycle_count += 1

        sup._run_cycle = mock_run_cycle

        # Run with MCPPool mocked out
        with patch("llm_rag.supervisor.loop.MCPPool") as mock_pool_cls:
            mock_pool = AsyncMock()
            mock_pool_cls.return_value = mock_pool
            mock_pool.__aenter__ = AsyncMock(return_value=mock_pool)
            mock_pool.__aexit__ = AsyncMock(return_value=False)

            task = asyncio.create_task(sup.run())
            await shutdown_after_delay()
            await asyncio.wait_for(task, timeout=5.0)

        assert cycle_count >= 1

    @pytest.mark.asyncio
    async def test_shutdown_timeout(self, tmp_path):
        """Verify that asyncio.wait_for can timeout a slow shutdown."""
        mgr = ShutdownManager()
        sup, state, state_file, pid_file = self._make_supervisor(tmp_path, shutdown_mgr=mgr)

        # Make graceful_shutdown hang
        original = sup.graceful_shutdown

        async def slow_shutdown(reason=None):
            await asyncio.sleep(100)  # much longer than timeout

        sup.graceful_shutdown = slow_shutdown

        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await asyncio.wait_for(sup.graceful_shutdown(), timeout=0.1)


class TestShutdownReasons:
    """Test ShutdownReason enum values."""

    def test_reason_values(self):
        assert ShutdownReason.SIGTERM.value == "SIGTERM"
        assert ShutdownReason.SIGINT.value == "SIGINT"
        assert ShutdownReason.SIGHUP.value == "SIGHUP"
        assert ShutdownReason.TIMEOUT.value == "timeout"
        assert ShutdownReason.MANUAL.value == "manual"
