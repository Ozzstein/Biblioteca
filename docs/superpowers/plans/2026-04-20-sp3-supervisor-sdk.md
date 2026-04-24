# SP3: Supervisor on SDK — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the LangGraph supervisor loop with a plain Python async loop that dispatches pipeline and reviewer subagents via the Agent SDK.

**Architecture:** `SupervisorAgent.run()` becomes an async loop that calls `_run_cycle()` each iteration. `_run_cycle()` calls `scan_pending_files` via the live MCP pool, drains the watchdog `file_queue`, runs all pending files in parallel via `asyncio.gather(PipelineRunner.run)`, then calls `_run_reviewer()`. The old `ReviewerAgent` class is deleted; a new `AgentDefinition` + `run_agent()` call replaces it. `SupervisorState`, `_scan_node`, `_process_one_node`, `_build_graph`, and the LangGraph import are all removed.

**Tech Stack:** Python asyncio, claude-code-sdk, FastMCP (mcp.server.fastmcp), anyio MCPPool, APScheduler (untouched)

---

## Files

**Modified:**
- `src/llm_rag/mcp/corpus_io.py` — add `scan_pending_files` tool
- `src/llm_rag/supervisor/loop.py` — full rewrite: async loop, no LangGraph
- `tests/supervisor/test_loop.py` — full rewrite: async tests, new interface
- `tests/mcp/test_corpus_io.py` — add 3 `scan_pending_files` tests
- `pyproject.toml` — remove `langgraph` dependency

**Created:**
- `agents/prompts/reviewer.md` — new SDK agent prompt for wiki review

**Deleted:**
- `src/llm_rag/supervisor/reviewer.py`
- `tests/supervisor/test_reviewer.py`

---

### Task 1: `scan_pending_files` MCP tool

**Files:**
- Modify: `src/llm_rag/mcp/corpus_io.py`
- Test: `tests/mcp/test_corpus_io.py`

`scan_pending_files` replaces the Python `_scan_node()` logic. It walks `settings.raw_dir`, skips `.manifest.json` sidecars, and includes any file whose manifest is missing or whose stages_completed list does not contain all five `ProcessingStage` values. `load_manifest` and `ProcessingStage` are already imported in `corpus_io.py` — no new imports needed.

The supervisor calls this tool via the live pool session:
```python
result = await self._pool.get("corpus-io").call_tool("scan_pending_files", {})
```
`call_tool` (from the `mcp` library's `ClientSession`) is async and returns a `CallToolResult`. The tool's dict return value is serialized to JSON in `result.content[0].text`.

- [ ] **Step 1: Write failing tests**

Append these three tests at the bottom of `tests/mcp/test_corpus_io.py`. Use a local import inside each test so the import line doesn't break the existing tests before the tool is implemented.

```python
async def test_scan_pending_files_finds_unprocessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    (raw / "doc.md").write_text("content")
    from llm_rag.mcp.corpus_io import scan_pending_files
    result = await scan_pending_files()
    assert str(raw / "doc.md") in result["pending_paths"]
    get_settings.cache_clear()


async def test_scan_pending_files_skips_fully_processed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    doc = raw / "done.md"
    doc.write_text("content")
    from llm_rag.pipeline.manifest import create_manifest, save_manifest as _save, update_stage
    from llm_rag.schemas.provenance import ProcessingStage
    manifest = create_manifest(doc, "papers/done", "papers", "manual")
    for stage in ProcessingStage:
        manifest = update_stage(manifest, stage)
    _save(manifest)
    from llm_rag.mcp.corpus_io import scan_pending_files
    result = await scan_pending_files()
    assert str(doc) not in result["pending_paths"]
    get_settings.cache_clear()


async def test_scan_pending_files_skips_manifest_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    (raw / "doc.manifest.json").write_text("{}")
    from llm_rag.mcp.corpus_io import scan_pending_files
    result = await scan_pending_files()
    assert all(".manifest.json" not in p for p in result["pending_paths"])
    get_settings.cache_clear()
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/mcp/test_corpus_io.py::test_scan_pending_files_finds_unprocessed tests/mcp/test_corpus_io.py::test_scan_pending_files_skips_fully_processed tests/mcp/test_corpus_io.py::test_scan_pending_files_skips_manifest_files -v
```
Expected: `ImportError` — `scan_pending_files` not yet defined.

- [ ] **Step 3: Add `scan_pending_files` to `corpus_io.py`**

Insert before the `def main()` line at the bottom of `src/llm_rag/mcp/corpus_io.py`:

```python
@app.tool()
async def scan_pending_files() -> dict[str, list[str]]:
    """Scan raw_dir for files that need processing. Returns {"pending_paths": [...]}."""
    settings = get_settings()
    pending: list[str] = []
    for path in settings.raw_dir.rglob("*"):
        if path.is_file() and not path.name.endswith(".manifest.json"):
            manifest = load_manifest(path)
            if manifest is None or not all(
                stage in manifest.stages_completed for stage in ProcessingStage
            ):
                pending.append(str(path))
    return {"pending_paths": pending}
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/mcp/test_corpus_io.py -v
```
Expected: all corpus_io tests pass (including the 3 new ones).

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/mcp/corpus_io.py tests/mcp/test_corpus_io.py
git commit -m "feat: add scan_pending_files MCP tool to corpus-io"
```

---

### Task 2: Reviewer agent prompt

**Files:**
- Create: `agents/prompts/reviewer.md`

This file instructs Claude to call `list_pages` and `read_page` from wiki-io, check each page for unclosed fence pairs, note factual contradictions, and report findings. No test needed — prompt files are integration-tested only via live API calls.

- [ ] **Step 1: Create `agents/prompts/reviewer.md`**

```markdown
You are the Reviewer Agent for the Battery Research OS.

Your task: review all wiki pages for lint issues and contradictions.

## Tools available

wiki-io:
- `list_pages(subdir="")` — list all .md files in the wiki. Returns paths relative to wiki/.
- `read_page(relative_path)` — return the raw markdown content of a wiki page.

## Procedure

1. Call `list_pages()` to get all wiki page paths.
2. For each path returned:
   a. Call `read_page(relative_path=<path>)` to read the content.
   b. Check for lint issues: every `<!-- auto-start: NAME -->` must have a matching `<!-- auto-end: NAME -->` in the same file. Every `<!-- human-start: NAME -->` must have a matching `<!-- human-end: NAME -->`.
   c. Note any factual contradictions (e.g., one page claims LFP capacity is 160 mAh/g while another claims 175 mAh/g for the same material under the same conditions).
3. Report all lint issues found: page path + which fence name is unclosed.
4. Report contradictions found: a one-line description of each.
5. If no issues exist, reply: `REVIEW COMPLETE: no issues found.`

## Rules

- Do not modify any wiki pages.
- Do not call any tool not listed above.
- If there are more than 10 pages, check all pages for lint issues but limit contradiction analysis to the first 10 pages.
```

- [ ] **Step 2: Verify file exists**

```bash
ls agents/prompts/reviewer.md
```
Expected: file listed.

- [ ] **Step 3: Commit**

```bash
git add agents/prompts/reviewer.md
git commit -m "feat: add reviewer agent prompt"
```

---

### Task 3: Rewrite `supervisor/loop.py` and `tests/supervisor/test_loop.py`

**Files:**
- Modify: `src/llm_rag/supervisor/loop.py`
- Modify: `tests/supervisor/test_loop.py`

This is the core of SP3. The new loop.py has no LangGraph, no `SupervisorState`, no `_scan_node`, no `_process_one_node`, no `_build_graph`. The new `SupervisorAgent.__init__` takes `(raw_dir, settings=None, interval_seconds=60, file_queue=None)` — no `runner` or `reviewer` args.

**Key technical note:** `self._pool.get("corpus-io").call_tool("scan_pending_files", {})` is async and returns an `mcp.types.CallToolResult`. The dict result from the FastMCP tool is serialized to JSON in `result.content[0].text`. Parse it with `json.loads`.

TDD order: write the new test file first (tests fail against old loop.py), then rewrite loop.py (tests pass).

- [ ] **Step 1: Replace `tests/supervisor/test_loop.py` with the new version**

Write this exact content to `tests/supervisor/test_loop.py`:

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

```
uv run pytest tests/supervisor/test_loop.py -v
```
Expected: several failures — `SupervisorAgent` constructor rejects the new call signature (old code requires `runner` and `reviewer` args) or `_run_cycle` / async `run` don't exist.

- [ ] **Step 3: Rewrite `src/llm_rag/supervisor/loop.py`**

Write this exact content to `src/llm_rag/supervisor/loop.py`:

```python
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
        if not raw_result.isError and raw_result.content:
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/supervisor/test_loop.py -v
```
Expected: all 9 tests pass.

- [ ] **Step 5: Run mypy**

```
uv run mypy src/llm_rag/supervisor/loop.py
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/llm_rag/supervisor/loop.py tests/supervisor/test_loop.py
git commit -m "feat: replace LangGraph supervisor loop with async SDK loop"
```

---

### Task 4: Delete `ReviewerAgent` and its tests

**Files:**
- Delete: `src/llm_rag/supervisor/reviewer.py`
- Delete: `tests/supervisor/test_reviewer.py`

The `ReviewerAgent` class is replaced by the `AgentDefinition` + `run_agent()` call in Task 3. The `anthropic` SDK import in `reviewer.py` is now unused by the supervisor.

- [ ] **Step 1: Delete both files**

```bash
rm src/llm_rag/supervisor/reviewer.py
rm tests/supervisor/test_reviewer.py
```

- [ ] **Step 2: Verify no remaining imports of reviewer**

```bash
grep -r "from llm_rag.supervisor.reviewer" src/ tests/
```
Expected: no output (loop.py no longer imports it after Task 3).

- [ ] **Step 3: Run full test suite**

```
uv run pytest tests/ -v
```
Expected: all tests pass. No tests import from `reviewer.py`.

- [ ] **Step 4: Commit**

```bash
git add -u src/llm_rag/supervisor/reviewer.py tests/supervisor/test_reviewer.py
git commit -m "chore: delete ReviewerAgent (replaced by reviewer SDK agent)"
```

---

### Task 5: Remove `langgraph` from `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

`loop.py` no longer imports from `langgraph`. Remove the dependency and update the lock file.

- [ ] **Step 1: Remove the langgraph line from `pyproject.toml`**

Find and delete this line from the `[project] dependencies` list in `pyproject.toml`:
```
    "langgraph>=0.2.0",
```

- [ ] **Step 2: Update the lock file**

```bash
uv sync --extra dev
```
Expected: `langgraph` removed from the lock file, all other deps unchanged.

- [ ] **Step 3: Verify langgraph is not importable**

```bash
uv run python -c "import langgraph" 2>&1 | head -3
```
Expected: `ModuleNotFoundError: No module named 'langgraph'`

- [ ] **Step 4: Run full test suite**

```
uv run pytest tests/ -v
```
Expected: all tests pass (no remaining langgraph imports anywhere in src/ or tests/).

- [ ] **Step 5: Run mypy**

```
uv run mypy src/
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: remove langgraph dependency (SP3 migration complete)"
```
