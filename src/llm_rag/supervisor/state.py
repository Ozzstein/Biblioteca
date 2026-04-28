"""Supervisor process state tracking via PID file and JSON state."""

from __future__ import annotations

import json
import os
import signal
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

STATE_DIR = Path.home() / ".llm-rag" / "supervisor"
STATE_FILE = STATE_DIR / "state.json"
PID_FILE = STATE_DIR / "supervisor.pid"


class HealthStatus(str, Enum):
    """Overall health status of the supervisor or a subagent."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class SubagentHealth:
    """Health tracking for a single subagent."""

    name: str
    last_run: str = ""
    total_runs: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_runs == 0:
            return 1.0
        return (self.total_runs - self.total_failures) / self.total_runs

    def record_success(self, timestamp: str) -> None:
        self.last_run = timestamp
        self.total_runs += 1
        self.consecutive_failures = 0

    def record_failure(self, timestamp: str) -> None:
        self.last_run = timestamp
        self.total_runs += 1
        self.total_failures += 1
        self.consecutive_failures += 1

    @property
    def status(self) -> HealthStatus:
        if self.consecutive_failures > 5:
            return HealthStatus.UNHEALTHY
        if self.consecutive_failures > 3:
            return HealthStatus.DEGRADED
        if self.total_runs > 0 and self.success_rate < 0.5:
            return HealthStatus.UNHEALTHY
        if self.total_runs > 0 and self.success_rate < 0.9:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "last_run": self.last_run,
            "total_runs": self.total_runs,
            "total_failures": self.total_failures,
            "consecutive_failures": self.consecutive_failures,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SubagentHealth:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SupervisorState:
    pid: int = 0
    start_time: str = ""
    last_heartbeat: str = ""
    files_processed: int = 0
    errors: int = 0
    pending_files: list[str] = field(default_factory=list)
    subagent_health: dict[str, SubagentHealth] = field(default_factory=dict)

    def heartbeat_age(self) -> float:
        """Seconds since last heartbeat. Returns inf if no heartbeat recorded."""
        if not self.last_heartbeat:
            return float("inf")
        last = datetime.fromisoformat(self.last_heartbeat)
        now = datetime.now(UTC)
        return (now - last).total_seconds()

    def is_healthy(self, threshold_seconds: float = 60.0) -> bool:
        """True if heartbeat is within threshold."""
        return self.heartbeat_age() <= threshold_seconds

    @property
    def error_rate(self) -> float:
        total = self.files_processed + self.errors
        if total == 0:
            return 0.0
        return self.errors / total

    @property
    def health_status(self) -> HealthStatus:
        """Overall health based on heartbeat, error rate, and subagent health."""
        age = self.heartbeat_age()

        # Heartbeat check
        if age > 300:
            return HealthStatus.UNHEALTHY
        if age > 60:
            heartbeat_status = HealthStatus.DEGRADED
        else:
            heartbeat_status = HealthStatus.HEALTHY

        # Error rate check
        if self.error_rate > 0.5:
            error_status = HealthStatus.UNHEALTHY
        elif self.error_rate > 0.1:
            error_status = HealthStatus.DEGRADED
        else:
            error_status = HealthStatus.HEALTHY

        # Subagent check — worst status wins
        subagent_status = HealthStatus.HEALTHY
        for sh in self.subagent_health.values():
            if sh.status == HealthStatus.UNHEALTHY:
                subagent_status = HealthStatus.UNHEALTHY
                break
            if sh.status == HealthStatus.DEGRADED:
                subagent_status = HealthStatus.DEGRADED

        # Return worst of all three
        for status in (heartbeat_status, error_status, subagent_status):
            if status == HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
        for status in (heartbeat_status, error_status, subagent_status):
            if status == HealthStatus.DEGRADED:
                return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict converts SubagentHealth to dicts already, but the keys
        # are preserved as strings — this works correctly.
        d["subagent_health"] = {
            name: sh.to_dict() for name, sh in self.subagent_health.items()
        }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> SupervisorState:
        # Handle subagent_health separately
        raw_health = data.pop("subagent_health", {})
        state = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        for name, sh_data in raw_health.items():
            state.subagent_health[name] = SubagentHealth.from_dict(sh_data)
        return state


def _ensure_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def save_state(state: SupervisorState, state_file: Path = STATE_FILE) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state.to_dict(), indent=2))


def load_state(state_file: Path = STATE_FILE) -> SupervisorState | None:
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text())
        return SupervisorState.from_dict(data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def save_pid(pid: int, pid_file: Path = PID_FILE) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid))


def load_pid(pid_file: Path = PID_FILE) -> int | None:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def clear_pid(pid_file: Path = PID_FILE) -> None:
    if pid_file.exists():
        pid_file.unlink()


def is_running(pid_file: Path = PID_FILE) -> bool:
    """Check if the supervisor process is alive by PID."""
    pid = load_pid(pid_file)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def send_stop_signal(pid_file: Path = PID_FILE) -> bool:
    """Send SIGTERM to the supervisor process. Returns True if signal was sent."""
    pid = load_pid(pid_file)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        clear_pid(pid_file)
        return False
