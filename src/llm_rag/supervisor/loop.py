from __future__ import annotations

import asyncio
import json
import logging
import queue
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from llm_rag.agent_runner import AgentDefinition, run_agent
from llm_rag.config import Settings, get_settings
from llm_rag.mcp.pool import MCPPool
from llm_rag.pipeline.runner import PipelineRunner
from llm_rag.research.coordinator import ResearchAgent, SourceSubagent
from llm_rag.research.subagents.arxiv import ArXivSubagent
from llm_rag.research.subagents.firecrawl import FirecrawlSubagent
from llm_rag.research.subagents.google_scholar import GoogleScholarSubagent
from llm_rag.research.subagents.openalex import OpenAlexSubagent
from llm_rag.research.subagents.pubmed import PubMedSubagent
from llm_rag.research.subagents.semantic_scholar import SemanticScholarSubagent
from llm_rag.research.subagents.unpaywall import UnpaywallSubagent
from llm_rag.supervisor.shutdown import ShutdownManager, ShutdownReason
from llm_rag.supervisor.state import SubagentHealth, SupervisorState, clear_pid, now_iso, save_state

logger = logging.getLogger(__name__)

# Maps config key → subagent class
_SUBAGENT_CLASSES: dict[str, type] = {
    "arxiv": ArXivSubagent,
    "semantic_scholar": SemanticScholarSubagent,
    "openalex": OpenAlexSubagent,
    "pubmed": PubMedSubagent,
    "unpaywall": UnpaywallSubagent,
    "firecrawl": FirecrawlSubagent,
    "google_scholar": GoogleScholarSubagent,
}


@dataclass
class SubagentResult:
    """Tracks the outcome of a single subagent execution."""

    source_name: str
    started_at: str
    finished_at: str = ""
    files_written: int = 0
    error: str | None = None


@dataclass
class SchedulerState:
    """Tracks all subagent execution results."""

    results: list[SubagentResult] = field(default_factory=list)
    last_run: dict[str, str] = field(default_factory=dict)

    def record(self, result: SubagentResult) -> None:
        self.results.append(result)
        self.last_run[result.source_name] = result.finished_at


def _parse_schedule(schedule_str: str) -> dict[str, int] | None:
    """Parse 'interval:hours=12' → {'hours': 12}. Returns None for 'on-demand'."""
    if schedule_str == "on-demand":
        return None
    parts = schedule_str.split(":", 1)
    if len(parts) != 2 or parts[0] != "interval":
        return None
    params: dict[str, int] = {}
    for part in parts[1].split(","):
        key, _, val = part.partition("=")
        params[key.strip()] = int(val.strip())
    return params


def _run_subagent_sync(
    topics: list[str],
    source_name: str,
    research_agent: ResearchAgent,
    scheduler_state: SchedulerState,
    supervisor_state: SupervisorState | None = None,
    state_file: Path | None = None,
) -> None:
    """Bridge: run async ResearchAgent.run() for a single subagent from a sync APScheduler job."""
    result = SubagentResult(
        source_name=source_name,
        started_at=datetime.now(UTC).isoformat(),
    )
    logger.info(
        "Subagent %s started", source_name,
        extra={"event": "subagent_start", "source_name": source_name},
    )
    try:
        written = asyncio.run(research_agent.run(topics, subagent_names=[source_name]))
        result.files_written = len(written)
        logger.info(
            "Subagent %s finished — %d files written", source_name, result.files_written,
            extra={"event": "subagent_finish", "source_name": source_name, "files_written": result.files_written},
        )
    except Exception as exc:
        logger.error(
            "Subagent %s failed: %s", source_name, exc,
            extra={"event": "subagent_error", "source_name": source_name, "error_detail": str(exc)},
        )
        result.error = str(exc)
    finally:
        result.finished_at = datetime.now(UTC).isoformat()
        scheduler_state.record(result)
        # Update per-subagent health tracking
        if supervisor_state is not None:
            if source_name not in supervisor_state.subagent_health:
                supervisor_state.subagent_health[source_name] = SubagentHealth(name=source_name)
            sh = supervisor_state.subagent_health[source_name]
            if result.error:
                sh.record_failure(result.finished_at)
                logger.warning(
                    "Subagent %s health: %s (consecutive failures: %d)",
                    source_name, sh.status.value, sh.consecutive_failures,
                    extra={"event": "health_change", "source_name": source_name, "health_status": sh.status.value},
                )
            else:
                sh.record_success(result.finished_at)
            if state_file is not None:
                save_state(supervisor_state, state_file)


def load_sources_config(settings: Settings) -> dict[str, Any]:
    """Load config/sources.yaml from the project root."""
    sources_path = settings.root_dir / "config" / "sources.yaml"
    if not sources_path.exists():
        logger.warning("sources.yaml not found at %s", sources_path)
        return {"research_topics": [], "subagents": {}}
    return yaml.safe_load(sources_path.read_text()) or {}


def _create_subagent(
    name: str,
    cfg: dict[str, Any],
    settings: Settings,
) -> SourceSubagent | None:
    """Create a single subagent instance from config. Returns None on failure."""
    cls = _SUBAGENT_CLASSES.get(name)
    if cls is None:
        logger.warning("Unknown subagent key: %s — skipping", name)
        return None

    # Subagents with max_results parameter
    if name in ("arxiv", "semantic_scholar", "openalex", "pubmed"):
        max_results = cfg.get("max_results_per_query", 20)
        return cls(max_results=max_results)
    # Subagents requiring API keys
    if name == "firecrawl":
        return cls(api_key=settings.firecrawl_api_key)
    if name == "unpaywall":
        return cls(email="battery-research-os@example.com")
    if name == "google_scholar":
        return cls(serpapi_key=settings.serpapi_key)
    return cls()


def build_research_agent(
    settings: Settings,
    sources_config: dict[str, Any],
) -> ResearchAgent:
    """Instantiate ResearchAgent with subagents from sources config."""
    subagents: list[SourceSubagent] = []
    for name, cfg in sources_config.get("subagents", {}).items():
        if not cfg.get("enabled", False):
            continue
        sub = _create_subagent(name, cfg, settings)
        if sub is not None:
            subagents.append(sub)
    return ResearchAgent(settings=settings, subagents=subagents)


# Keep for backwards compatibility with existing tests
def _run_research_sync(topics: list[str], agent: Any) -> None:
    """Bridge: run async ResearchAgent.run() from a sync APScheduler job thread."""
    asyncio.run(agent.run(topics))


class SupervisorAgent:
    def __init__(
        self,
        raw_dir: Path,
        settings: Settings | None = None,
        interval_seconds: int = 60,
        file_queue: queue.Queue[Path] | None = None,
        supervisor_state: SupervisorState | None = None,
        state_file: Path | None = None,
        shutdown_manager: ShutdownManager | None = None,
        pid_file: Path | None = None,
    ) -> None:
        self.raw_dir = raw_dir
        self.settings: Settings = settings or get_settings()
        self.interval_seconds = interval_seconds
        self.file_queue: queue.Queue[Path] = file_queue or queue.Queue()
        self._pool: MCPPool | None = None
        self._reviewer = AgentDefinition(
            name="reviewer",
            model=self.settings.model_contradiction,
            mcp_servers=["wiki-io"],
            max_tokens=8192,
        )
        self._scheduler: Any = None
        self._research_agent: ResearchAgent | None = None
        self._scheduler_state: SchedulerState = SchedulerState()
        self._supervisor_state: SupervisorState | None = supervisor_state
        self._state_file: Path | None = state_file
        self._heartbeat_interval: float = 30.0
        self._shutdown_manager: ShutdownManager = shutdown_manager or ShutdownManager()
        self._pid_file: Path | None = pid_file

    async def _run_reviewer(self) -> None:
        assert self._pool is not None
        await run_agent(
            self._reviewer,
            "Review all wiki pages for lint issues and contradictions. Report any findings.",
            self.settings,
            self._pool,
        )

    def _update_heartbeat(self) -> None:
        """Update heartbeat timestamp and persist state."""
        if self._supervisor_state is not None:
            self._supervisor_state.last_heartbeat = now_iso()
            if self._state_file is not None:
                save_state(self._supervisor_state, self._state_file)

    async def _run_cycle(self) -> None:
        if self._shutdown_manager.is_shutting_down:
            logger.info("Shutdown in progress — skipping cycle")
            return

        assert self._pool is not None
        raw_result = await self._pool.get("corpus-io").call_tool("scan_pending_files", {})
        pending: list[str] = []
        if raw_result.isError:
            logger.warning("scan_pending_files returned an error; skipping MCP-sourced pending list")
        elif raw_result.content:
            text = getattr(raw_result.content[0], "text", None)
            if text:
                pending = json.loads(text).get("pending_paths", [])

        while not self.file_queue.empty():
            pending.append(str(self.file_queue.get_nowait()))

        if not pending:
            self._update_heartbeat()
            return

        logger.info(
            "Processing cycle: %d pending files", len(pending),
            extra={"event": "cycle_start", "files_written": len(pending)},
        )

        if self._supervisor_state is not None:
            self._supervisor_state.pending_files = pending

        async with PipelineRunner(self.settings) as runner:
            for p in pending:
                if self._shutdown_manager.is_shutting_down:
                    logger.info("Shutdown requested — stopping file processing")
                    break
                try:
                    await runner.run(Path(p))
                    if self._supervisor_state is not None:
                        self._supervisor_state.files_processed += 1
                    logger.debug(
                        "Processed file: %s", p,
                        extra={"event": "file_processed", "doc_id": p},
                    )
                except Exception:
                    if self._supervisor_state is not None:
                        self._supervisor_state.errors += 1
                    logger.error(
                        "Failed to process file: %s", p,
                        extra={"event": "file_error", "doc_id": p},
                        exc_info=True,
                    )
                    raise

        if self._supervisor_state is not None:
            self._supervisor_state.pending_files = []

        if not self._shutdown_manager.is_shutting_down:
            await self._run_reviewer()
        self._update_heartbeat()

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep that can be interrupted by the shutdown event."""
        evt = self._shutdown_manager.get_async_event()
        try:
            await asyncio.wait_for(evt.wait(), timeout=seconds)
        except TimeoutError:
            pass  # normal expiration

    async def run(self, max_iterations: int | None = None) -> None:
        logger.info(
            "Supervisor loop starting (interval=%ds, max_iterations=%s)",
            self.interval_seconds, max_iterations,
            extra={"event": "supervisor_start"},
        )
        async with MCPPool() as self._pool:
            iterations = 0
            self._update_heartbeat()
            while max_iterations is None or iterations < max_iterations:
                if self._shutdown_manager.is_shutting_down:
                    break
                await self._run_cycle()
                iterations += 1
                if self._shutdown_manager.is_shutting_down:
                    break
                if max_iterations is None or iterations < max_iterations:
                    await self._interruptible_sleep(min(self.interval_seconds, self._heartbeat_interval))
        logger.info("Supervisor loop stopped", extra={"event": "supervisor_stop"})

    async def graceful_shutdown(self, reason: ShutdownReason | None = None) -> None:
        """Perform a graceful shutdown sequence.

        1. Stop scheduler (no new jobs)
        2. Wait for pending files to finish (up to SHUTDOWN_TIMEOUT)
        3. Save final state with shutdown reason
        4. Clear PID file
        """
        if reason is not None and not self._shutdown_manager.is_shutting_down:
            self._shutdown_manager.request_shutdown(reason)

        shutdown_reason = self._shutdown_manager.reason or ShutdownReason.MANUAL
        logger.info(
            "Graceful shutdown initiated (reason=%s)", shutdown_reason.value,
            extra={"event": "shutdown_start", "reason": shutdown_reason.value},
        )

        # Step 1: stop scheduler
        logger.info("Shutdown step 1/4: stopping scheduler")
        self.stop_scheduler()

        # Step 2: wait for any in-flight cycle to finish (up to timeout)
        logger.info("Shutdown step 2/4: waiting for pending work to complete")
        # The _run_cycle checks is_shutting_down and will stop processing

        # Step 3: save final state
        logger.info("Shutdown step 3/4: saving final state (reason=%s)", shutdown_reason.value)
        if self._supervisor_state is not None:
            self._supervisor_state.last_heartbeat = now_iso()
            if self._state_file is not None:
                save_state(self._supervisor_state, self._state_file)

        # Step 4: clear PID file
        logger.info("Shutdown step 4/4: clearing PID file")
        if self._pid_file is not None:
            clear_pid(self._pid_file)

        logger.info(
            "Shutdown complete (reason=%s)", shutdown_reason.value,
            extra={"event": "shutdown_complete", "reason": shutdown_reason.value},
        )

    def init_research(
        self,
        sources_config: dict[str, Any] | None = None,
    ) -> ResearchAgent:
        """Initialize ResearchAgent from sources config.

        If sources_config is not provided, loads from config/sources.yaml.
        """
        if sources_config is None:
            sources_config = load_sources_config(self.settings)
        self._research_agent = build_research_agent(self.settings, sources_config)
        return self._research_agent

    def start_scheduler(
        self,
        topics: list[str],
        sources_config: dict[str, Any],
        research_agent: ResearchAgent | Any | None = None,
    ) -> None:
        """Start APScheduler with per-subagent jobs.

        Each enabled subagent with an interval schedule gets its own job that
        calls ResearchAgent.run() filtered to just that subagent.
        """
        if research_agent is not None:
            self._research_agent = research_agent
        elif self._research_agent is None:
            self._research_agent = build_research_agent(self.settings, sources_config)

        self._scheduler = BackgroundScheduler()
        for source_name, config in sources_config.get("subagents", {}).items():
            if not config.get("enabled", False):
                continue
            schedule_str = config.get("schedule", "on-demand")
            params = _parse_schedule(schedule_str)
            if params is None:
                continue
            self._scheduler.add_job(
                _run_subagent_sync,
                IntervalTrigger(**params),
                id=source_name,
                args=[topics, source_name, self._research_agent, self._scheduler_state],
                kwargs={
                    "supervisor_state": self._supervisor_state,
                    "state_file": self._state_file,
                },
            )
        self._scheduler.start()

    def stop_scheduler(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
