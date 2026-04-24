# SP6: CLI Integration — Design Spec

**Date:** 2026-04-20
**Status:** Approved

---

## Goal

Wire all `llm-rag` commands to the agent layer built in SP1–SP5. A single `src/llm_rag/cli.py` with a Typer app, 9 sub-commands, a global `--debug` flag, and rich terminal output.

---

## What This Builds

- `src/llm_rag/cli.py` — Typer app with all 9 commands
- `tests/cli/__init__.py` — empty package init
- `tests/cli/test_ask.py` — 3 tests
- `tests/cli/test_ingest.py` — 3 tests
- `tests/cli/test_status.py` — 2 tests

**Modified:**
- `src/llm_rag/config.py` — add `unpaywall_email` field
- `.env.example` — add `UNPAYWALL_EMAIL=` line

`pyproject.toml` already has `llm-rag = "llm_rag.cli:app"` — no change needed.

---

## What This Does Not Build

- Telegram bot — that is SP7
- `--mode` routing flags on `ask` — deferred to SP7
- `--quality` flag on `ask` — deferred to SP7

---

## Section 1: Global Structure

```python
import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Battery Research OS CLI")
console = Console()
_debug: bool = False

@app.callback()
def main(debug: bool = typer.Option(False, "--debug")) -> None:
    global _debug
    _debug = debug
```

Every command wraps its body:

```python
try:
    ...
except Exception as exc:
    if _debug:
        raise
    console.print(f"[red]Error:[/red] {exc}")
    raise typer.Exit(1)
```

Settings are loaded via `get_settings()` at the top of each command. If `ANTHROPIC_API_KEY` is missing, pydantic-settings leaves it as `""` — commands that need it check and raise a clear error before invoking any agent.

---

## Section 2: `ask` Command

```python
@app.command()
def ask(
    query: str = typer.Argument(..., help="Question to ask"),
    verbose: bool = typer.Option(False, "--verbose", help="Show sources"),
) -> None:
```

**Implementation:**

```python
async def _ask(query: str, verbose: bool) -> None:
    settings = get_settings()
    async with MCPPool() as pool:
        agent = QueryAgent(settings=settings)
        result = await agent.ask(query, pool)
    console.print(Markdown(result.answer))
    if verbose and result.sources:
        console.print("\n[bold]Sources[/bold]")
        for src in result.sources:
            console.print(f"  [dim]·[/dim] {src}")
```

`Markdown` is `rich.markdown.Markdown`. The answer is rendered with headers, bold, and code blocks. Sources are printed as a dim bulleted list below the answer.

---

## Section 3: `run` Command

```python
@app.command()
def run(
    interval: int = typer.Option(60, "--interval", help="Poll interval in seconds"),
) -> None:
```

**Implementation:**

Runs `SupervisorAgent.run()` via `asyncio.run()`. Uses `rich.logging.RichHandler` so supervisor log output is nicely formatted. Shows a persistent spinner while the loop is active:

```python
import logging
from rich.logging import RichHandler
from rich.spinner import Spinner
from rich import print as rprint

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=_debug)],
)

settings = get_settings()
agent = SupervisorAgent(
    raw_dir=settings.raw_dir,
    settings=settings,
    interval_seconds=interval,
)
console.print("[green]Supervisor starting...[/green] Press Ctrl+C to stop.")
asyncio.run(agent.run())
```

`KeyboardInterrupt` is caught and exits cleanly (no error message, exit 0).

---

## Section 4: `ingest` Command

```python
@app.command()
def ingest(
    path: Path | None = typer.Option(None, "--path"),
    doc_id: str | None = typer.Option(None, "--doc-id"),
    force: bool = typer.Option(False, "--force"),
) -> None:
```

**Implementation:**

```python
settings = get_settings()
runner = PipelineRunner(settings=settings)

if doc_id:
    # Find source file by doc_id — walk raw/ for matching manifest
    manifest_path = _find_source_by_doc_id(settings.raw_dir, doc_id)
    if manifest_path is None:
        console.print(f"[red]Error:[/red] No file found for doc_id {doc_id!r}")
        raise typer.Exit(1)
    paths = [manifest_path]
elif path:
    paths = list(path.rglob("*"))
    paths = [p for p in paths if p.is_file() and not p.name.endswith(".manifest.json")]
else:
    paths = list(settings.raw_dir.rglob("*"))
    paths = [p for p in paths if p.is_file() and not p.name.endswith(".manifest.json")]

for p in paths:
    console.print(f"Ingesting [cyan]{p.relative_to(settings.root_dir)}[/cyan]")
    asyncio.run(runner.run(p, force=force))
```

`_find_source_by_doc_id(raw_dir, doc_id) -> Path | None` walks `raw_dir` for `*.manifest.json` files, reads each, returns the `source_path` for the one whose `doc_id` matches.

---

## Section 5: `fetch` Command

```python
@app.command()
def fetch(
    topic: str | None = typer.Option(None, "--topic"),
    doi: str | None = typer.Option(None, "--doi"),
    url: str | None = typer.Option(None, "--url"),
    source: str | None = typer.Option(None, "--source"),
) -> None:
```

**Implementation:**

`--doi` and `--url` bypass `ResearchAgent` entirely — `UnpaywallSubagent.search()` and `FirecrawlSubagent.search()` both return `[]` (they are fetch-only subagents). Instead, a `CandidateDocument` is constructed directly and fetched:

```python
settings = get_settings()
inbox = settings.raw_dir / "inbox"
inbox.mkdir(parents=True, exist_ok=True)

if doi:
    from llm_rag.research.subagents.unpaywall import UnpaywallSubagent
    from llm_rag.research.coordinator import CandidateDocument
    candidate = CandidateDocument(title=doi, abstract="", doi=doi)
    subagent = UnpaywallSubagent(email=settings.unpaywall_email)
    result = asyncio.run(subagent.fetch(candidate))
    if result is None:
        console.print(f"[yellow]No open-access PDF found for DOI {doi}[/yellow]")
    else:
        content, ext = result
        out = inbox / f"{doi.replace('/', '-')}.{ext}"
        out.write_bytes(content)
        console.print(f"Saved to [cyan]{out}[/cyan]")

elif url:
    from llm_rag.research.subagents.firecrawl import FirecrawlSubagent
    from llm_rag.research.coordinator import CandidateDocument
    candidate = CandidateDocument(title=url, abstract="", source_url=url)
    subagent = FirecrawlSubagent(api_key=settings.firecrawl_api_key)
    result = asyncio.run(subagent.fetch(candidate))
    if result is None:
        console.print(f"[yellow]Could not fetch URL {url}[/yellow]")
    else:
        content, ext = result
        slug = url.split("//")[-1].replace("/", "-")[:60]
        out = inbox / f"{slug}.{ext}"
        out.write_bytes(content)
        console.print(f"Saved to [cyan]{out}[/cyan]")

else:
    from llm_rag.research.subagents.arxiv import ArXivSubagent
    from llm_rag.research.subagents.semantic_scholar import SemanticScholarSubagent
    from llm_rag.research.subagents.openalex import OpenAlexSubagent
    from llm_rag.research.subagents.pubmed import PubMedSubagent

    _SEARCH_SUBAGENTS: dict[str, Any] = {
        "arxiv": ArXivSubagent(),
        "semantic_scholar": SemanticScholarSubagent(),
        "openalex": OpenAlexSubagent(),
        "pubmed": PubMedSubagent(),
    }

    if source:
        if source not in _SEARCH_SUBAGENTS:
            console.print(f"[red]Error:[/red] Unknown source {source!r}. Valid: {', '.join(_SEARCH_SUBAGENTS)}")
            raise typer.Exit(1)
        subagents = [_SEARCH_SUBAGENTS[source]]
    else:
        subagents = list(_SEARCH_SUBAGENTS.values())

    topics = [topic] if topic else _load_topics(settings)
    agent = ResearchAgent(settings=settings, subagents=subagents)
    written = asyncio.run(agent.run(topics=topics))
    console.print(f"Fetched [bold]{len(written)}[/bold] document(s)")
```

`_load_topics(settings) -> list[str]` reads `config/sources.yaml` and returns the `research_topics` list.

`UnpaywallSubagent` requires an email address (Unpaywall API requirement). This is added to `Settings` as `unpaywall_email: str = Field(default="", alias="UNPAYWALL_EMAIL")` — add to `src/llm_rag/config.py`. Also add `UNPAYWALL_EMAIL=` to `.env.example`.

---

## Section 6: `compile-wiki` Command

```python
@app.command("compile-wiki")
def compile_wiki(
    entity: str | None = typer.Option(None, "--entity"),
) -> None:
```

**Implementation:**

Finds all manifest files missing `wiki_compiled` in `stages_completed` and re-runs the pipeline (which picks up from the last completed stage):

```python
settings = get_settings()
runner = PipelineRunner(settings=settings)
manifests = _load_all_manifests(settings.raw_dir)

if entity:
    manifests = [m for m in manifests if m["doc_id"] == entity]

targets = [m for m in manifests if "wiki_compiled" not in m.get("stages_completed", [])]
console.print(f"Compiling wiki for [bold]{len(targets)}[/bold] document(s)")
for m in targets:
    source = Path(m["source_path"])
    console.print(f"  [cyan]{m['doc_id']}[/cyan]")
    asyncio.run(runner.run(source))
```

`_load_all_manifests(raw_dir) -> list[dict]` walks `raw_dir` for `*.manifest.json` files and returns parsed dicts.

---

## Section 7: `build-graph` Command

```python
@app.command("build-graph")
def build_graph(
    rebuild: bool = typer.Option(False, "--rebuild"),
) -> None:
```

Same pattern as `compile-wiki` but filters on `graph_updated` stage. `--rebuild` passes `force=True` to `runner.run()`.

---

## Section 8: `status` Command

```python
@app.command()
def status() -> None:
```

**Implementation:**

```python
from rich.table import Table

settings = get_settings()
manifests = _load_all_manifests(settings.raw_dir)
stage_counts: dict[str, int] = {}
for m in manifests:
    for stage in m.get("stages_completed", []):
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

table = Table(title="Corpus Status")
table.add_column("Stage")
table.add_column("Count", justify="right")
for stage in ["ingested", "extracted", "normalized", "wiki_compiled", "graph_updated"]:
    table.add_row(stage, str(stage_counts.get(stage, 0)))
table.add_row("[bold]Total docs[/bold]", f"[bold]{len(manifests)}[/bold]")
console.print(table)
```

---

## Section 9: `lint-wiki` Command

```python
@app.command("lint-wiki")
def lint_wiki(
    fix: bool = typer.Option(False, "--fix"),
) -> None:
```

**Implementation:**

Walk `wiki/` for `*.md` files. For each, call `wiki.reader.parse_page(path)` — if it raises, the page has a broken fence. With `--fix`: rewrite the file stripping broken fences. Without `--fix`: print the file path and error.

```python
from llm_rag.wiki.reader import parse_page

settings = get_settings()
issues = 0
for md_file in settings.wiki_dir.rglob("*.md"):
    try:
        parse_page(md_file)
    except Exception as exc:
        issues += 1
        console.print(f"[yellow]WARN[/yellow] {md_file.relative_to(settings.root_dir)}: {exc}")
        if fix:
            console.print(f"  [dim]→ skipping auto-fix (not yet implemented)[/dim]")
console.print(f"\n[bold]{issues}[/bold] issue(s) found")
```

Auto-fix is deferred — `--fix` prints a "not yet implemented" note per file. This gives the flag the right shape for SP7 to fill in without breaking the CLI contract.

---

## Section 10: `export-graph` Command

```python
@app.command("export-graph")
def export_graph(
    format: str = typer.Option("graphml", "--format", help="graphml or cypher"),
) -> None:
```

**Implementation:**

```python
from llm_rag.graph.store import GraphStore

settings = get_settings()
snapshot = settings.graph_dir / "snapshots" / "latest.graphml"
if not snapshot.exists():
    console.print("[red]Error:[/red] No graph snapshot found. Run `llm-rag build-graph` first.")
    raise typer.Exit(1)

store = GraphStore(snapshot_path=snapshot)
store.load()

if format == "graphml":
    import networkx as nx
    out = settings.graph_dir / "exports" / "export.graphml"
    out.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(store.graph, out)
    console.print(f"Exported GraphML to [cyan]{out}[/cyan]")
elif format == "cypher":
    console.print("[red]Error:[/red] Cypher export not yet implemented")
    raise typer.Exit(1)
else:
    console.print(f"[red]Error:[/red] Unknown format {format!r}. Use graphml or cypher.")
    raise typer.Exit(1)
```

---

## Section 11: Shared Helpers

Three private helpers used across commands:

```python
def _load_all_manifests(raw_dir: Path) -> list[dict]:
    """Walk raw_dir for *.manifest.json files and return parsed dicts."""
    import json
    results = []
    for p in raw_dir.rglob("*.manifest.json"):
        try:
            results.append(json.loads(p.read_text()))
        except Exception:
            pass
    return results


def _find_source_by_doc_id(raw_dir: Path, doc_id: str) -> Path | None:
    """Return source_path from the manifest matching doc_id, or None."""
    for m in _load_all_manifests(raw_dir):
        if m.get("doc_id") == doc_id:
            return Path(m["source_path"])
    return None


def _load_topics(settings: Settings) -> list[str]:
    """Read research_topics from config/sources.yaml."""
    import yaml
    sources_yaml = settings.config_dir / "sources.yaml"
    if not sources_yaml.exists():
        return []
    data = yaml.safe_load(sources_yaml.read_text())
    return data.get("research_topics", [])
```

---

## Section 12: Testing

### `tests/cli/test_ask.py` — 3 tests

```python
from typer.testing import CliRunner
from unittest.mock import AsyncMock, MagicMock, patch
from llm_rag.cli import app

runner = CliRunner()

def test_ask_renders_answer():
    mock_result = MagicMock()
    mock_result.answer = "LFP capacity fade is caused by SEI growth."
    mock_result.sources = ["wiki/mechanisms/sei.md §evidence"]
    with patch("llm_rag.cli.QueryAgent") as mock_cls, \
         patch("llm_rag.cli.MCPPool") as mock_pool_cls:
        mock_pool_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_pool_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value.ask = AsyncMock(return_value=mock_result)
        result = runner.invoke(app, ["ask", "What causes LFP fade?"])
    assert result.exit_code == 0
    assert "SEI growth" in result.output


def test_ask_verbose_shows_sources():
    mock_result = MagicMock()
    mock_result.answer = "LFP capacity fade is caused by SEI growth."
    mock_result.sources = ["wiki/mechanisms/sei.md §evidence"]
    with patch("llm_rag.cli.QueryAgent") as mock_cls, \
         patch("llm_rag.cli.MCPPool") as mock_pool_cls:
        mock_pool_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_pool_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value.ask = AsyncMock(return_value=mock_result)
        result = runner.invoke(app, ["ask", "--verbose", "What causes LFP fade?"])
    assert result.exit_code == 0
    assert "sei.md" in result.output


def test_ask_error_shows_clean_message():
    with patch("llm_rag.cli.QueryAgent") as mock_cls, \
         patch("llm_rag.cli.MCPPool") as mock_pool_cls:
        mock_pool_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_pool_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value.ask = AsyncMock(side_effect=RuntimeError("API unavailable"))
        result = runner.invoke(app, ["ask", "query"])
    assert result.exit_code == 1
    assert "API unavailable" in result.output
    assert "Traceback" not in result.output
```

### `tests/cli/test_ingest.py` — 3 tests

```python
def test_ingest_processes_all_files(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    (raw / "doc.md").write_text("content")
    with patch("llm_rag.cli.PipelineRunner") as mock_cls:
        mock_cls.return_value.run = AsyncMock(return_value=MagicMock())
        result = runner.invoke(app, ["ingest"])
    assert result.exit_code == 0
    mock_cls.return_value.run.assert_called_once()
    get_settings.cache_clear()


def test_ingest_force_flag_passed_through(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    (raw / "doc.md").write_text("content")
    with patch("llm_rag.cli.PipelineRunner") as mock_cls:
        mock_cls.return_value.run = AsyncMock(return_value=MagicMock())
        result = runner.invoke(app, ["ingest", "--force"])
    assert result.exit_code == 0
    mock_cls.return_value.run.assert_called_once()
    _, kwargs = mock_cls.return_value.run.call_args
    assert kwargs.get("force") is True
    get_settings.cache_clear()


def test_ingest_unknown_doc_id_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (tmp_path / "raw").mkdir()
    result = runner.invoke(app, ["ingest", "--doc-id", "papers/no-such-doc"])
    assert result.exit_code == 1
    assert "No file found" in result.output
    get_settings.cache_clear()
```

### `tests/cli/test_status.py` — 2 tests

```python
def test_status_shows_stage_counts(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    raw = tmp_path / "raw" / "papers"
    raw.mkdir(parents=True)
    manifest = {"doc_id": "papers/lfp-001", "source_path": str(raw / "lfp-001.md"),
                "stages_completed": ["ingested", "extracted"]}
    (raw / "lfp-001.manifest.json").write_text(json.dumps(manifest))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "ingested" in result.output
    assert "1" in result.output
    get_settings.cache_clear()


def test_status_empty_corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (tmp_path / "raw").mkdir()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "0" in result.output
    get_settings.cache_clear()
```

---

## File Layout Summary

**Created:**
```
src/llm_rag/cli.py
tests/cli/__init__.py
tests/cli/test_ask.py
tests/cli/test_ingest.py
tests/cli/test_status.py
```

**Modified:**
```
src/llm_rag/config.py    — add unpaywall_email field
.env.example             — add UNPAYWALL_EMAIL= line
```
