"""Tests for supervisor state tracking."""

from pathlib import Path

from llm_rag.supervisor.state import (
    SupervisorState,
    clear_pid,
    is_running,
    load_pid,
    load_state,
    save_pid,
    save_state,
)


def test_supervisor_state_defaults():
    state = SupervisorState()
    assert state.pid == 0
    assert state.start_time == ""
    assert state.last_heartbeat == ""
    assert state.files_processed == 0
    assert state.errors == 0
    assert state.pending_files == []


def test_state_to_dict_roundtrip():
    state = SupervisorState(
        pid=1234,
        start_time="2026-04-24T10:00:00+00:00",
        last_heartbeat="2026-04-24T10:01:00+00:00",
        files_processed=5,
        errors=1,
        pending_files=["raw/inbox/test.pdf"],
    )
    d = state.to_dict()
    restored = SupervisorState.from_dict(d)
    assert restored.pid == 1234
    assert restored.files_processed == 5
    assert restored.errors == 1
    assert restored.pending_files == ["raw/inbox/test.pdf"]


def test_save_and_load_state(tmp_path: Path):
    state_file = tmp_path / "state.json"
    state = SupervisorState(
        pid=42,
        start_time="2026-04-24T10:00:00+00:00",
        last_heartbeat="2026-04-24T10:05:00+00:00",
        files_processed=3,
    )
    save_state(state, state_file)
    loaded = load_state(state_file)
    assert loaded is not None
    assert loaded.pid == 42
    assert loaded.files_processed == 3


def test_load_state_missing_file(tmp_path: Path):
    assert load_state(tmp_path / "nonexistent.json") is None


def test_load_state_corrupt_file(tmp_path: Path):
    state_file = tmp_path / "state.json"
    state_file.write_text("not json")
    assert load_state(state_file) is None


def test_save_and_load_pid(tmp_path: Path):
    pid_file = tmp_path / "supervisor.pid"
    save_pid(9999, pid_file)
    assert load_pid(pid_file) == 9999


def test_load_pid_missing_file(tmp_path: Path):
    assert load_pid(tmp_path / "nonexistent.pid") is None


def test_clear_pid(tmp_path: Path):
    pid_file = tmp_path / "supervisor.pid"
    save_pid(9999, pid_file)
    assert pid_file.exists()
    clear_pid(pid_file)
    assert not pid_file.exists()


def test_clear_pid_missing_file(tmp_path: Path):
    clear_pid(tmp_path / "nonexistent.pid")  # should not raise


def test_is_running_no_pid_file(tmp_path: Path):
    assert is_running(tmp_path / "nonexistent.pid") is False


def test_is_running_stale_pid(tmp_path: Path):
    pid_file = tmp_path / "supervisor.pid"
    save_pid(999999, pid_file)  # very unlikely to be a real PID
    assert is_running(pid_file) is False


def test_is_running_current_process(tmp_path: Path):
    import os

    pid_file = tmp_path / "supervisor.pid"
    save_pid(os.getpid(), pid_file)
    assert is_running(pid_file) is True


def test_from_dict_ignores_extra_keys():
    state = SupervisorState.from_dict({"pid": 1, "unknown_key": "value"})
    assert state.pid == 1
