"""Tests for MCPPool restart-on-crash with exponential backoff (A3A).

Covers the retry loop in ``MCPPool._run_server`` without spawning real
subprocesses. ``_run_server_once`` is monkey-patched per scenario to script
the crash/recovery sequence.
"""

from __future__ import annotations

import sys

import anyio
import pytest

from llm_rag.mcp.pool import (
    MCPPool,
    MCPServerConfig,
    SourceUnavailable,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dummy_cfg(name: str = "test-source") -> MCPServerConfig:
    """A config that is never actually executed (we patch _run_server_once)."""
    return MCPServerConfig(
        name=name,
        command=[sys.executable, "-c", "pass"],
    )


# ---------------------------------------------------------------------------
# Restart-on-crash behavior
# ---------------------------------------------------------------------------


async def test_recovers_after_one_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """First spawn crashes; second succeeds. Source should end up available."""
    # Speed up the test by zeroing the backoff schedule.
    monkeypatch.setattr(
        "llm_rag.mcp.pool._BACKOFF_SCHEDULE", (0.0, 0.0, 0.0, 0.0, 0.0)
    )

    attempts: list[int] = []
    fake_session_obj = object()

    async def scripted_once(self: MCPPool, cfg: MCPServerConfig, ready_event: anyio.Event) -> None:
        attempt_idx = len(attempts)
        attempts.append(attempt_idx)
        if attempt_idx == 0:
            raise RuntimeError("simulated crash")
        # Subsequent spawn succeeds: register a fake session and block.
        self._sessions[cfg.name] = fake_session_obj  # type: ignore[assignment]
        ready_event.set()
        await anyio.sleep_forever()

    monkeypatch.setattr(MCPPool, "_run_server_once", scripted_once)

    pool = MCPPool(servers=[_dummy_cfg("flaky")], max_restarts=3)
    async with pool:
        # Wait long enough for the second spawn to register.
        with anyio.fail_after(2.0):
            while "flaky" not in pool._sessions:
                await anyio.sleep(0.01)
        assert pool.get("flaky") is fake_session_obj
        assert "flaky" not in pool.unavailable
    assert len(attempts) >= 2  # at least one crash + one success


async def test_marked_unavailable_after_max_restarts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash on every attempt → source ends up marked unavailable."""
    monkeypatch.setattr(
        "llm_rag.mcp.pool._BACKOFF_SCHEDULE", (0.0, 0.0, 0.0, 0.0, 0.0)
    )

    async def always_crashes(self: MCPPool, cfg: MCPServerConfig, ready_event: anyio.Event) -> None:
        raise RuntimeError("hard failure")

    monkeypatch.setattr(MCPPool, "_run_server_once", always_crashes)

    pool = MCPPool(servers=[_dummy_cfg("doomed")], max_restarts=2)
    async with pool:
        # Pool entered: ready_event must have been set even though we never succeeded,
        # so __aenter__ does not hang on a permanently unavailable source.
        with anyio.fail_after(2.0):
            while "doomed" not in pool.unavailable:
                await anyio.sleep(0.01)
        assert "doomed" in pool.unavailable
        assert "hard failure" in pool.unavailable["doomed"]
        with pytest.raises(SourceUnavailable):
            pool.get("doomed")


async def test_source_unavailable_is_keyerror_subclass() -> None:
    """Existing KeyError-catching code keeps working; new code can catch the subclass."""
    assert issubclass(SourceUnavailable, KeyError)


async def test_max_restarts_zero_disables_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_restarts=0 → first crash immediately marks source unavailable."""
    monkeypatch.setattr(
        "llm_rag.mcp.pool._BACKOFF_SCHEDULE", (0.0, 0.0, 0.0, 0.0, 0.0)
    )

    attempts: list[None] = []

    async def crashes_once(self: MCPPool, cfg: MCPServerConfig, ready_event: anyio.Event) -> None:
        attempts.append(None)
        raise RuntimeError("nope")

    monkeypatch.setattr(MCPPool, "_run_server_once", crashes_once)

    pool = MCPPool(servers=[_dummy_cfg("once")], max_restarts=0)
    async with pool:
        with anyio.fail_after(2.0):
            while "once" not in pool.unavailable:
                await anyio.sleep(0.01)
    assert len(attempts) == 1  # no retries with cap=0


async def test_unavailable_property_returns_copy() -> None:
    """unavailable should not expose internal mutable state."""
    pool = MCPPool(servers=[_dummy_cfg("x")])
    pool._unavailable["x"] = "test"
    snapshot = pool.unavailable
    snapshot["x"] = "mutated"
    assert pool._unavailable["x"] == "test"


# ---------------------------------------------------------------------------
# Healthy-startup smoke
# ---------------------------------------------------------------------------


async def test_healthy_startup_no_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful spawn → unavailable dict stays empty."""

    async def succeeds(self: MCPPool, cfg: MCPServerConfig, ready_event: anyio.Event) -> None:
        self._sessions[cfg.name] = object()  # type: ignore[assignment]
        ready_event.set()
        await anyio.sleep_forever()

    monkeypatch.setattr(MCPPool, "_run_server_once", succeeds)

    pool = MCPPool(servers=[_dummy_cfg("ok-1"), _dummy_cfg("ok-2")])
    async with pool:
        assert pool.unavailable == {}
        assert pool.get("ok-1") is not None
        assert pool.get("ok-2") is not None
