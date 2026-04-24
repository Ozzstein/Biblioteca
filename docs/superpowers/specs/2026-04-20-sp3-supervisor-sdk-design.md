# SP3: Supervisor on SDK — Design Spec

**Date:** 2026-04-20
**Status:** Approved

---

## Goal

Replace the LangGraph `StateGraph` supervisor loop with a plain Python async loop. Dispatch pipeline and reviewer subagents via the Agent SDK. Keep APScheduler and watchdog exactly as-is.

## Architecture

### What changes

- `SupervisorAgent` loses its LangGraph `StateGraph`, `_scan_node`, `_process_one_node`, `_build_graph`, and sync `run()` method
- `SupervisorState` TypedDict is deleted
- `ReviewerAgent` class and `src/llm_rag/supervisor/reviewer.py` are deleted
- `run()` becomes `async def`, owns an `MCPPool` for its lifetime
- New `_run_cycle()` coroutine replaces the graph nodes
- New `_run_reviewer()` coroutine dispatches the reviewer as an SDK agent
- `scan_pending_files` MCP tool added to corpus-io replaces `_scan_node` Python logic

### What stays

- APScheduler (`start_scheduler`, `stop_scheduler`) — untouched
- watchdog `file_queue` — still drained inside `_run_cycle()`
- `PipelineRunner` async context manager — used per-cycle

---

## Section 1: Delete LangGraph

Remove all LangGraph dependencies from `supervisor/loop.py`:

- Delete `from langgraph.graph import StateGraph, END`
- Delete `SupervisorState` TypedDict
- Delete `_scan_node`, `_process_one_node`, `_build_graph`
- Delete sync `run()` method
- Remove `langgraph` from `pyproject.toml` dependencies

---

## Section 2: `corpus-io.scan_pending_files` MCP Tool

New tool added to `src/llm_rag/mcp/corpus_io.py`:

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

The supervisor calls this directly via the live MCP session:

```python
raw = await self._pool.get("corpus-io").call_tool("scan_pending_files", {})
pending: list[str] = raw.get("pending_paths", [])
```

---

## Section 3: New `_run_cycle()` Method

Replaces the LangGraph scan → process flow:

```python
async def _run_cycle(self) -> None:
    raw = await self._pool.get("corpus-io").call_tool("scan_pending_files", {})
    pending: list[str] = raw.get("pending_paths", [])

    # drain the live file_queue (watchdog drop-zone)
    while not self.file_queue.empty():
        pending.append(str(self.file_queue.get_nowait()))

    if not pending:
        return

    async with PipelineRunner(self.settings) as runner:
        await asyncio.gather(*(runner.run(Path(p)) for p in pending))

    await self._run_reviewer()
```

The outer `run()` loop:

```python
async def run(self, max_iterations: int | None = None) -> None:
    async with MCPPool() as self._pool:
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            await self._run_cycle()
            iterations += 1
            if max_iterations is None or iterations < max_iterations:
                await asyncio.sleep(self.interval_seconds)
```

---

## Section 4: Reviewer as SDK Agent

`ReviewerAgent` class and `src/llm_rag/supervisor/reviewer.py` are deleted. A new `AgentDefinition` replaces it:

```python
self._reviewer = AgentDefinition(
    "reviewer",
    self.settings.model_contradiction,
    ["wiki-io"],
    max_tokens=8192,
)
```

`_run_reviewer()`:

```python
async def _run_reviewer(self) -> None:
    await run_agent(
        self._reviewer,
        "Review all wiki pages for lint issues and contradictions. Report any findings.",
        self.settings,
        self._pool,
    )
```

New `agents/prompts/reviewer.md` instructs Claude to call `list_pages` (wiki-io), read each page via `get_page`, check for lint issues and contradictions, and report findings. The structured `ReviewReport` dataclass is deleted — Claude's text output replaces it.

---

## Section 5: `SupervisorAgent` Constructor + Lifecycle

```python
class SupervisorAgent:
    def __init__(
        self,
        raw_dir: Path,
        settings: Settings | None = None,
        interval_seconds: int = 60,
        file_queue: queue.Queue[Path] | None = None,
    ) -> None:
        self.raw_dir = raw_dir
        self.settings = settings or get_settings()
        self.interval_seconds = interval_seconds
        self.file_queue: queue.Queue[Path] = file_queue or queue.Queue()
        self._pool: MCPPool | None = None
        self._reviewer = AgentDefinition(
            "reviewer",
            self.settings.model_contradiction,
            ["wiki-io"],
            max_tokens=8192,
        )
        self._scheduler: BackgroundScheduler | None = None
```

`runner` and `reviewer` are no longer constructor arguments. `PipelineRunner` is constructed inside `_run_cycle()` per-cycle. `start_scheduler` and `stop_scheduler` are unchanged.

---

## Section 6: Testing Changes

### `tests/supervisor/test_loop.py` — rewritten

`_make_agent` drops `runner` and `reviewer` arguments:

```python
def _make_agent(tmp_path: Path, **kwargs: object) -> SupervisorAgent:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return SupervisorAgent(raw_dir=raw_dir, interval_seconds=0, **kwargs)
```

**Deleted tests** (methods no longer exist):
- `test_scan_finds_unprocessed_file`
- `test_scan_skips_fully_processed_file`
- `test_scan_drains_file_queue`
- `test_scan_skips_manifest_files`
- `test_process_one_calls_runner`
- `test_process_one_handles_runner_error`
- `test_build_graph_returns_compiled_graph`
- `test_run_processes_pending_file`
- `test_run_no_files_does_not_call_runner`

**New tests:**

- `test_run_cycle_calls_scan_and_gather` — mocks `pool.get("corpus-io").call_tool` to return `{"pending_paths": [str(doc)]}`, mocks `PipelineRunner.run` as `AsyncMock`, verifies `run` called once per path
- `test_run_cycle_drains_file_queue` — puts a path in `file_queue`, verifies it's included in gather
- `test_run_cycle_empty_skips_runner` — scan returns empty, verifies `PipelineRunner.run` never called
- `test_run_iterates_max_iterations` — `max_iterations=2`, mocks `_run_cycle`, verifies called twice

**Unchanged tests:**
- `test_parse_schedule_*`
- `test_start_scheduler_registers_enabled_jobs`
- `test_stop_scheduler_shuts_down`

### `tests/supervisor/test_reviewer.py` — deleted

### `tests/mcp/test_corpus_io.py` — additions

- `test_scan_pending_files_finds_unprocessed`
- `test_scan_pending_files_skips_fully_processed`
- `test_scan_pending_files_skips_manifest_files`

---

## File Layout Summary

**Deleted:**
```
src/llm_rag/supervisor/reviewer.py
tests/supervisor/test_reviewer.py
```

**Modified:**
```
src/llm_rag/supervisor/loop.py        — async run(), _run_cycle(), _run_reviewer(), no LangGraph, no ReviewerAgent import
src/llm_rag/mcp/corpus_io.py          — add scan_pending_files tool
tests/supervisor/test_loop.py         — async tests, no LangGraph node tests
tests/mcp/test_corpus_io.py           — add scan_pending_files tests
agents/prompts/reviewer.md            — new SDK agent prompt
pyproject.toml                         — remove langgraph dependency
```
