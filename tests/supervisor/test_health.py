"""Tests for supervisor health monitoring and heartbeat tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_rag.supervisor.state import (
    HealthStatus,
    SubagentHealth,
    SupervisorState,
    load_state,
    save_state,
)


# --- HealthStatus enum ---


def test_health_status_values():
    assert HealthStatus.HEALTHY == "healthy"
    assert HealthStatus.DEGRADED == "degraded"
    assert HealthStatus.UNHEALTHY == "unhealthy"


# --- SubagentHealth ---


def test_subagent_health_defaults():
    sh = SubagentHealth(name="arxiv")
    assert sh.name == "arxiv"
    assert sh.last_run == ""
    assert sh.total_runs == 0
    assert sh.total_failures == 0
    assert sh.consecutive_failures == 0
    assert sh.success_rate == 1.0
    assert sh.status == HealthStatus.HEALTHY


def test_subagent_health_record_success():
    sh = SubagentHealth(name="arxiv")
    sh.record_success("2026-04-24T10:00:00+00:00")
    assert sh.total_runs == 1
    assert sh.total_failures == 0
    assert sh.consecutive_failures == 0
    assert sh.last_run == "2026-04-24T10:00:00+00:00"
    assert sh.success_rate == 1.0


def test_subagent_health_record_failure():
    sh = SubagentHealth(name="arxiv")
    sh.record_failure("2026-04-24T10:00:00+00:00")
    assert sh.total_runs == 1
    assert sh.total_failures == 1
    assert sh.consecutive_failures == 1
    assert sh.success_rate == 0.0


def test_subagent_health_consecutive_failures_reset():
    sh = SubagentHealth(name="arxiv")
    sh.record_failure("2026-04-24T10:00:00+00:00")
    sh.record_failure("2026-04-24T10:01:00+00:00")
    assert sh.consecutive_failures == 2
    sh.record_success("2026-04-24T10:02:00+00:00")
    assert sh.consecutive_failures == 0
    assert sh.total_failures == 2  # total stays


def test_subagent_health_status_degraded_by_consecutive_failures():
    sh = SubagentHealth(name="arxiv")
    for i in range(4):
        sh.record_failure(f"2026-04-24T10:0{i}:00+00:00")
    assert sh.consecutive_failures == 4
    assert sh.status == HealthStatus.DEGRADED


def test_subagent_health_status_unhealthy_by_consecutive_failures():
    sh = SubagentHealth(name="arxiv")
    for i in range(6):
        sh.record_failure(f"2026-04-24T10:0{i}:00+00:00")
    assert sh.consecutive_failures == 6
    assert sh.status == HealthStatus.UNHEALTHY


def test_subagent_health_status_degraded_by_success_rate():
    sh = SubagentHealth(name="arxiv")
    # 8 successes, 2 failures = 80% success rate (< 90%)
    for i in range(8):
        sh.record_success(f"2026-04-24T10:0{i}:00+00:00")
    sh.record_failure("2026-04-24T10:08:00+00:00")
    sh.record_failure("2026-04-24T10:09:00+00:00")
    # consecutive_failures = 2 (not > 3), success_rate = 0.8 (< 0.9)
    assert sh.consecutive_failures == 2
    assert sh.success_rate == 0.8
    assert sh.status == HealthStatus.DEGRADED


def test_subagent_health_status_unhealthy_by_success_rate():
    sh = SubagentHealth(name="arxiv")
    # 1 success, 3 failures = 25% success rate
    sh.record_success("2026-04-24T10:00:00+00:00")
    sh.record_failure("2026-04-24T10:01:00+00:00")
    sh.record_failure("2026-04-24T10:02:00+00:00")
    sh.record_failure("2026-04-24T10:03:00+00:00")
    # consecutive_failures = 3 (not > 3, not > 5), success_rate = 0.25 (< 0.5)
    assert sh.success_rate == 0.25
    assert sh.status == HealthStatus.UNHEALTHY


def test_subagent_health_to_dict_roundtrip():
    sh = SubagentHealth(name="arxiv", total_runs=10, total_failures=2, consecutive_failures=1)
    d = sh.to_dict()
    restored = SubagentHealth.from_dict(d)
    assert restored.name == "arxiv"
    assert restored.total_runs == 10
    assert restored.total_failures == 2
    assert restored.consecutive_failures == 1


# --- SupervisorState heartbeat ---


def test_heartbeat_age_no_heartbeat():
    state = SupervisorState()
    assert state.heartbeat_age() == float("inf")


def test_heartbeat_age_recent():
    now = datetime.now(timezone.utc)
    state = SupervisorState(last_heartbeat=now.isoformat())
    age = state.heartbeat_age()
    assert age < 2.0  # should be nearly 0


def test_heartbeat_age_old():
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    state = SupervisorState(last_heartbeat=old.isoformat())
    age = state.heartbeat_age()
    assert 119 < age < 125


def test_is_healthy_within_threshold():
    now = datetime.now(timezone.utc)
    state = SupervisorState(last_heartbeat=now.isoformat())
    assert state.is_healthy(threshold_seconds=60.0) is True


def test_is_healthy_outside_threshold():
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    state = SupervisorState(last_heartbeat=old.isoformat())
    assert state.is_healthy(threshold_seconds=60.0) is False


def test_is_healthy_no_heartbeat():
    state = SupervisorState()
    assert state.is_healthy() is False


# --- SupervisorState error_rate ---


def test_error_rate_no_activity():
    state = SupervisorState()
    assert state.error_rate == 0.0


def test_error_rate_calculation():
    state = SupervisorState(files_processed=9, errors=1)
    assert abs(state.error_rate - 0.1) < 0.01


# --- SupervisorState health_status ---


def test_health_status_healthy():
    now = datetime.now(timezone.utc)
    state = SupervisorState(
        last_heartbeat=now.isoformat(),
        files_processed=100,
        errors=5,
    )
    assert state.health_status == HealthStatus.HEALTHY


def test_health_status_degraded_by_heartbeat():
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    state = SupervisorState(
        last_heartbeat=old.isoformat(),
        files_processed=100,
        errors=0,
    )
    assert state.health_status == HealthStatus.DEGRADED


def test_health_status_unhealthy_by_heartbeat():
    old = datetime.now(timezone.utc) - timedelta(seconds=400)
    state = SupervisorState(
        last_heartbeat=old.isoformat(),
        files_processed=100,
        errors=0,
    )
    assert state.health_status == HealthStatus.UNHEALTHY


def test_health_status_degraded_by_error_rate():
    now = datetime.now(timezone.utc)
    state = SupervisorState(
        last_heartbeat=now.isoformat(),
        files_processed=7,
        errors=3,  # 30% error rate
    )
    assert state.health_status == HealthStatus.DEGRADED


def test_health_status_unhealthy_by_error_rate():
    now = datetime.now(timezone.utc)
    state = SupervisorState(
        last_heartbeat=now.isoformat(),
        files_processed=3,
        errors=7,  # 70% error rate
    )
    assert state.health_status == HealthStatus.UNHEALTHY


def test_health_status_degraded_by_subagent():
    now = datetime.now(timezone.utc)
    sh = SubagentHealth(name="arxiv")
    for i in range(4):
        sh.record_failure(f"2026-04-24T10:0{i}:00+00:00")
    state = SupervisorState(
        last_heartbeat=now.isoformat(),
        files_processed=100,
        errors=0,
        subagent_health={"arxiv": sh},
    )
    assert state.health_status == HealthStatus.DEGRADED


def test_health_status_unhealthy_by_subagent():
    now = datetime.now(timezone.utc)
    sh = SubagentHealth(name="arxiv")
    for i in range(6):
        sh.record_failure(f"2026-04-24T10:0{i}:00+00:00")
    state = SupervisorState(
        last_heartbeat=now.isoformat(),
        files_processed=100,
        errors=0,
        subagent_health={"arxiv": sh},
    )
    assert state.health_status == HealthStatus.UNHEALTHY


# --- SupervisorState serialization with subagent_health ---


def test_state_with_subagent_health_roundtrip(tmp_path: Path):
    sh = SubagentHealth(name="arxiv", total_runs=5, total_failures=1)
    state = SupervisorState(
        pid=1234,
        start_time="2026-04-24T10:00:00+00:00",
        last_heartbeat="2026-04-24T10:01:00+00:00",
        files_processed=10,
        errors=2,
        subagent_health={"arxiv": sh},
    )
    state_file = tmp_path / "state.json"
    save_state(state, state_file)
    loaded = load_state(state_file)
    assert loaded is not None
    assert "arxiv" in loaded.subagent_health
    assert loaded.subagent_health["arxiv"].total_runs == 5
    assert loaded.subagent_health["arxiv"].total_failures == 1
    assert loaded.subagent_health["arxiv"].name == "arxiv"


def test_state_from_dict_no_subagent_health():
    """Backwards compat: old state files without subagent_health."""
    state = SupervisorState.from_dict({
        "pid": 1,
        "start_time": "",
        "last_heartbeat": "",
        "files_processed": 0,
        "errors": 0,
        "pending_files": [],
    })
    assert state.subagent_health == {}


def test_state_from_dict_with_subagent_health():
    state = SupervisorState.from_dict({
        "pid": 1,
        "subagent_health": {
            "arxiv": {
                "name": "arxiv",
                "last_run": "2026-04-24T10:00:00+00:00",
                "total_runs": 3,
                "total_failures": 1,
                "consecutive_failures": 0,
            }
        },
    })
    assert "arxiv" in state.subagent_health
    assert state.subagent_health["arxiv"].total_runs == 3
