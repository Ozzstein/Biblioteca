from __future__ import annotations

import asyncio
import json
import logging
import queue
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from llm_rag.agent_runner import AgentDefinition, run_agent
from llm_rag.config import Settings, get_settings
from llm_rag.mcp.pool import MCPPool
from llm_rag.pipeline.runner import PipelineRunner

logger = logging.getLogger(__name__)


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

    async def _run_reviewer(self) -> None:
        assert self._pool is not None
        await run_agent(
            self._reviewer,
            "Review all wiki pages for lint issues and contradictions. Report any findings.",
            self.settings,
            self._pool,
        )

    async def _run_cycle(self) -> None:
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
            return

        async with PipelineRunner(self.settings) as runner:
            await asyncio.gather(*(runner.run(Path(p)) for p in pending))

        await self._run_reviewer()

    async def run(self, max_iterations: int | None = None) -> None:
        async with MCPPool() as self._pool:
            iterations = 0
            while max_iterations is None or iterations < max_iterations:
                await self._run_cycle()
                iterations += 1
                if max_iterations is None or iterations < max_iterations:
                    await asyncio.sleep(self.interval_seconds)

    def start_scheduler(
        self,
        topics: list[str],
        sources_config: dict[str, Any],
        research_agent: Any,
    ) -> None:
        self._scheduler = BackgroundScheduler()
        for source_name, config in sources_config.get("subagents", {}).items():
            if not config.get("enabled", False):
                continue
            schedule_str = config.get("schedule", "on-demand")
            params = _parse_schedule(schedule_str)
            if params is None:
                continue
            self._scheduler.add_job(
                _run_research_sync,
                IntervalTrigger(**params),
                id=source_name,
                args=[topics, research_agent],
            )
        self._scheduler.start()

    def stop_scheduler(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
