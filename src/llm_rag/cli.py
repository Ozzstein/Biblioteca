"""Typer CLI entry point for llm-rag."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
import typer

from llm_rag.config import get_settings

app = typer.Typer(name="llm-rag")
pipeline_app = typer.Typer(name="pipeline", help="Pipeline processing commands.")
app.add_typer(pipeline_app, name="pipeline")
supervisor_app = typer.Typer(name="supervisor", help="Supervisor daemon commands.")
app.add_typer(supervisor_app, name="supervisor")


def _resolve_source_path(
    path: str | None, doc_id: str | None
) -> Path:
    """Turn --path or --doc-id into an absolute source Path."""
    settings = get_settings()
    if path is not None:
        p = Path(path)
        return p if p.is_absolute() else Path.cwd() / p
    if doc_id is not None:
        # doc_id like "papers/sample-lfp-001" → raw/papers/sample-lfp-001.*
        base = settings.raw_dir / doc_id
        # Try common extensions
        for ext in (".md", ".pdf", ".txt", ""):
            candidate = base.with_suffix(ext) if ext else base
            if candidate.exists():
                return candidate
        # Fall back to the extensionless path and let PipelineRunner error
        return base
    # Default: process all of raw/inbox/
    return settings.raw_dir / "inbox"


async def _run_pipeline(source_path: Path, force: bool = False) -> None:
    from llm_rag.pipeline.runner import PipelineRunner

    runner = PipelineRunner()
    async with runner:
        await runner.run(source_path, force=force)


@app.callback()
def main() -> None:
    """Battery Research OS — autonomous research assistant."""


@app.command()
def status() -> None:
    """Show system status."""
    settings = get_settings()
    typer.echo("Battery Research OS — Status")
    typer.echo("─" * 40)

    # Paths
    typer.echo(f"Root dir:       {settings.root_dir}")
    typer.echo(f"Raw dir:        {settings.raw_dir}")
    typer.echo(f"Wiki dir:       {settings.wiki_dir}")
    typer.echo(f"Graph dir:      {settings.graph_dir}")
    typer.echo(f"Retrieval dir:  {settings.retrieval_dir}")

    # API keys (presence only)
    typer.echo("")
    typer.echo("API Keys:")
    typer.echo(f"  ANTHROPIC_API_KEY:  {'set' if settings.anthropic_api_key else 'NOT SET'}")
    typer.echo(f"  FIRECRAWL_API_KEY:  {'set' if settings.firecrawl_api_key else 'NOT SET'}")
    typer.echo(f"  SERPAPI_KEY:         {'set' if settings.serpapi_key else 'NOT SET'}")

    # Model assignments
    typer.echo("")
    typer.echo("Models:")
    typer.echo(f"  Bulk extraction:    {settings.model_bulk_extraction}")
    typer.echo(f"  Wiki compilation:   {settings.model_wiki_compilation}")
    typer.echo(f"  Query synthesis:    {settings.model_query_synthesis}")
    typer.echo(f"  Deep analysis:      {settings.model_deep_analysis}")
    typer.echo(f"  Contradiction:      {settings.model_contradiction}")
    typer.echo(f"  Relevance scoring:  {settings.model_relevance_scoring}")
    typer.echo(f"  Supervisor:         {settings.model_supervisor}")

    # Pipeline settings
    typer.echo("")
    typer.echo("Pipeline:")
    typer.echo(f"  Chunk size:         {settings.chunk_size} tokens")
    typer.echo(f"  Chunk overlap:      {settings.chunk_overlap} tokens")
    typer.echo(f"  Relevance threshold:{settings.relevance_threshold}")
    typer.echo(f"  Supervisor interval:{settings.supervisor_interval_seconds}s")

    # Directory stats
    typer.echo("")
    typer.echo("Corpus:")
    raw_dir = settings.raw_dir
    wiki_dir = settings.wiki_dir
    graph_exports = settings.graph_dir / "exports"
    raw_count = len(list(raw_dir.rglob("*"))) if raw_dir.exists() else 0
    wiki_count = len(list(wiki_dir.rglob("*.md"))) if wiki_dir.exists() else 0
    export_count = len(list(graph_exports.rglob("*.json"))) if graph_exports.exists() else 0
    typer.echo(f"  Raw files:          {raw_count}")
    typer.echo(f"  Wiki pages:         {wiki_count}")
    typer.echo(f"  Graph exports:      {export_count}")


@app.command()
def ingest(
    path: str | None = typer.Option(None, help="Path to ingest (e.g. raw/inbox/)"),
    doc_id: str | None = typer.Option(None, "--doc-id", help="Process one specific document by ID"),
    force: bool = typer.Option(False, help="Reprocess regardless of content hash"),
) -> None:
    """Ingest raw documents into the pipeline."""
    source_path = _resolve_source_path(path, doc_id)
    typer.echo(f"Ingesting {source_path} ...")
    try:
        asyncio.run(_run_pipeline(source_path, force=force))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    typer.echo("Ingest complete.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="The question to ask"),
    mode: str | None = typer.Option(None, click_type=click.Choice(["wiki", "vector", "graph", "hybrid"], case_sensitive=False), help="Routing mode"),
    quality: bool = typer.Option(False, help="Use Opus for deep analysis"),
    verbose: bool = typer.Option(False, help="Show retrieval trace + provenance citations"),
) -> None:
    """Ask a question against the knowledge base."""
    async def _run_query() -> "QueryResult":
        from llm_rag.mcp.pool import MCPPool
        from llm_rag.query.agent import QueryAgent

        settings = get_settings()
        agent = QueryAgent(settings)
        async with MCPPool() as pool:
            return await agent.ask(question, pool)

    try:
        query_result = asyncio.run(_run_query())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    typer.echo(query_result.answer)
    if query_result.sources:
        typer.echo("")
        typer.echo("## Sources")
        for src in query_result.sources:
            typer.echo(f"- {src}")


# --- Materialize commands ---

materialize_app = typer.Typer(name="materialize", help="Rebuild derived surfaces from canonical records.")
app.add_typer(materialize_app, name="materialize")


def _load_claims(input_dir: Path) -> list["ClaimCollection"]:
    """Load all ClaimCollection JSON files from a directory."""
    import json

    from llm_rag.knowledge.models import ClaimCollection

    collections: list[ClaimCollection] = []
    if not input_dir.exists():
        return collections
    for p in sorted(input_dir.rglob("*.json")):
        try:
            data = json.loads(p.read_text())
            # Only parse files that look like claim collections
            if "source_doc_id" in data and ("claims" in data or "entity_claims" in data):
                collections.append(ClaimCollection.model_validate(data))
        except Exception:
            continue
    return collections


def _load_evidence(input_dir: Path) -> list["EvidenceStore"]:
    """Load all EvidenceStore JSON files from a directory."""
    import json

    from llm_rag.evidence.models import EvidenceStore

    stores: list[EvidenceStore] = []
    if not input_dir.exists():
        return stores
    for p in sorted(input_dir.rglob("*.json")):
        try:
            data = json.loads(p.read_text())
            if "document" in data and "chunks" in data:
                stores.append(EvidenceStore.model_validate(data))
        except Exception:
            continue
    return stores


def _run_materialize_graph(
    input_dir: Path, output_dir: Path, force: bool = False
) -> int:
    """Materialize the graph from claims. Returns node count."""
    import networkx as nx

    from llm_rag.graph.materializer import GraphMaterializer
    from llm_rag.knowledge.models import EntityClaim, RelationClaim

    snapshot_path = output_dir / "snapshots" / "latest.graphml"
    if snapshot_path.exists() and not force:
        typer.echo(f"Graph snapshot already exists at {snapshot_path}. Use --force to overwrite.")
        raise SystemExit(1)

    settings = get_settings()
    norm_path = settings.config_dir / "entity-normalization.yaml"

    if norm_path.exists():
        materializer = GraphMaterializer.from_normalization_yaml(norm_path)
    else:
        materializer = GraphMaterializer()

    collections = _load_claims(input_dir)
    all_entity_claims: list[EntityClaim] = []
    all_relation_claims: list[RelationClaim] = []
    for coll in collections:
        all_entity_claims.extend(coll.entity_claims)
        all_relation_claims.extend(coll.relation_claims)

    g = materializer.build_graph_from_claims(all_entity_claims, all_relation_claims)

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(g, str(snapshot_path))

    return g.number_of_nodes()


def _run_materialize_wiki(
    input_dir: Path, output_dir: Path, force: bool = False
) -> int:
    """Materialize wiki pages from claims + evidence. Returns page count."""
    from llm_rag.wiki.materializer import WikiMaterializer

    settings = get_settings()
    template_dir = settings.config_dir / "page-templates"

    collections = _load_claims(input_dir)
    evidence_stores = _load_evidence(input_dir)

    materializer = WikiMaterializer(
        wiki_dir=output_dir,
        template_dir=template_dir,
    )

    # Build a lookup of evidence by doc_id
    evidence_by_doc: dict[str, "EvidenceStore"] = {}
    for es in evidence_stores:
        evidence_by_doc[es.document.doc_id] = es

    pages_written = 0
    for coll in collections:
        # Get evidence for this collection's document
        from llm_rag.evidence.models import EvidenceDocument, EvidenceStore

        evidence = evidence_by_doc.get(
            coll.source_doc_id,
            EvidenceStore(
                document=EvidenceDocument(
                    doc_id=coll.source_doc_id,
                    source_path=f"raw/{coll.source_doc_id}",
                    doc_type="other",
                    content_hash="sha256:unknown",
                    ingested_at=coll.extracted_at,
                ),
                chunks=[],
            ),
        )

        # Materialize pages for each unique entity in this collection
        seen_entities: set[str] = set()
        for ec in coll.entity_claims:
            if ec.entity_id in seen_entities:
                continue
            seen_entities.add(ec.entity_id)

            # Derive path from entity type and ID
            entity_type_dir = ec.entity_type.value.lower() + "s"
            entity_slug = ec.entity_id.split(":", 1)[-1] if ":" in ec.entity_id else ec.entity_id
            relative_path = f"{entity_type_dir}/{entity_slug}.md"
            page_path = output_dir / relative_path

            if page_path.exists() and not force:
                continue

            materializer.build_wiki_page(
                entity_id=ec.entity_id,
                entity_type=ec.entity_type.value.lower(),
                canonical_name=entity_slug.replace("-", " ").title(),
                claims=coll,
                evidence=evidence,
                relative_path=relative_path,
            )
            pages_written += 1

    return pages_written


@materialize_app.callback()
def materialize_main() -> None:
    """Rebuild derived surfaces from canonical records."""


@materialize_app.command("graph")
def materialize_graph(
    input_dir: str | None = typer.Option(None, "--input", help="Source directory for claims JSON"),
    output_dir: str | None = typer.Option(None, "--output", help="Output directory for graph"),
    force: bool = typer.Option(False, help="Overwrite existing outputs"),
) -> None:
    """Rebuild the knowledge graph from canonical claim records."""
    settings = get_settings()
    inp = Path(input_dir) if input_dir else settings.graph_dir / "exports"
    out = Path(output_dir) if output_dir else settings.graph_dir

    typer.echo(f"Materializing graph from {inp} ...")
    try:
        node_count = _run_materialize_graph(inp, out, force=force)
    except SystemExit:
        raise
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    typer.echo(f"Graph materialized: {node_count} nodes.")


@materialize_app.command("wiki")
def materialize_wiki(
    input_dir: str | None = typer.Option(None, "--input", help="Source directory for claims/evidence JSON"),
    output_dir: str | None = typer.Option(None, "--output", help="Output directory for wiki pages"),
    force: bool = typer.Option(False, help="Overwrite existing outputs"),
) -> None:
    """Rebuild wiki pages from canonical claim and evidence records."""
    settings = get_settings()
    inp = Path(input_dir) if input_dir else settings.graph_dir / "exports"
    out = Path(output_dir) if output_dir else settings.wiki_dir

    typer.echo(f"Materializing wiki from {inp} ...")
    try:
        page_count = _run_materialize_wiki(inp, out, force=force)
    except SystemExit:
        raise
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    typer.echo(f"Wiki materialized: {page_count} pages.")


@materialize_app.command("all")
def materialize_all(
    input_dir: str | None = typer.Option(None, "--input", help="Source directory for claims/evidence JSON"),
    force: bool = typer.Option(False, help="Overwrite existing outputs"),
) -> None:
    """Rebuild both graph and wiki from canonical records."""
    settings = get_settings()
    inp = Path(input_dir) if input_dir else settings.graph_dir / "exports"

    typer.echo(f"Materializing all surfaces from {inp} ...")
    try:
        node_count = _run_materialize_graph(inp, settings.graph_dir, force=force)
        typer.echo(f"Graph materialized: {node_count} nodes.")
        page_count = _run_materialize_wiki(inp, settings.wiki_dir, force=force)
        typer.echo(f"Wiki materialized: {page_count} pages.")
    except SystemExit:
        raise
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    typer.echo("All surfaces materialized.")


# --- Aliases ---

@app.command("build-graph")
def build_graph(
    input_dir: str | None = typer.Option(None, "--input", help="Source directory for claims JSON"),
    output_dir: str | None = typer.Option(None, "--output", help="Output directory for graph"),
    force: bool = typer.Option(False, help="Overwrite existing outputs"),
) -> None:
    """Rebuild the knowledge graph (alias for materialize graph)."""
    materialize_graph(input_dir=input_dir, output_dir=output_dir, force=force)


@app.command("compile-wiki")
def compile_wiki(
    input_dir: str | None = typer.Option(None, "--input", help="Source directory for claims/evidence JSON"),
    output_dir: str | None = typer.Option(None, "--output", help="Output directory for wiki pages"),
    force: bool = typer.Option(False, help="Overwrite existing outputs"),
) -> None:
    """Rebuild wiki pages (alias for materialize wiki)."""
    materialize_wiki(input_dir=input_dir, output_dir=output_dir, force=force)


# --- Pipeline commands ---

@pipeline_app.callback()
def pipeline_main() -> None:
    """Pipeline processing commands."""


@pipeline_app.command()
def run(
    path: str | None = typer.Option(None, help="Path to process (e.g. raw/papers/my-paper.md)"),
    force: bool = typer.Option(False, help="Reprocess regardless of content hash"),
) -> None:
    """Run the full processing pipeline."""
    source_path = _resolve_source_path(path, doc_id=None)
    typer.echo(f"Running pipeline on {source_path} ...")
    try:
        asyncio.run(_run_pipeline(source_path, force=force))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    typer.echo("Pipeline complete.")


# --- Supervisor commands ---


@supervisor_app.callback()
def supervisor_main() -> None:
    """Supervisor daemon commands."""


@supervisor_app.command("start")
def supervisor_start(
    interval: int = typer.Option(60, help="Poll interval in seconds"),
    foreground: bool = typer.Option(False, help="Run in foreground (don't daemonize)"),
) -> None:
    """Start the autonomous supervisor loop."""
    import os
    import signal

    import yaml

    from llm_rag.supervisor.shutdown import ShutdownManager, ShutdownReason
    from llm_rag.supervisor.state import (
        SupervisorState,
        is_running,
        now_iso,
        save_pid,
        save_state,
    )

    settings = get_settings()
    pid_file = settings.root_dir / ".supervisor" / "supervisor.pid"
    state_file = settings.root_dir / ".supervisor" / "state.json"

    if is_running(pid_file):
        typer.echo("Supervisor is already running.")
        raise SystemExit(1)

    # Load sources config
    sources_path = settings.config_dir / "sources.yaml"
    if sources_path.exists():
        sources_config = yaml.safe_load(sources_path.read_text()) or {}
    else:
        sources_config = {}

    topics = [t["query"] for t in sources_config.get("research_topics", []) if "query" in t]

    if not foreground:
        # Fork into background
        child_pid = os.fork()
        if child_pid != 0:
            # Parent: save PID and exit
            save_pid(child_pid, pid_file)
            state = SupervisorState(
                pid=child_pid,
                start_time=now_iso(),
                last_heartbeat=now_iso(),
            )
            save_state(state, state_file)
            typer.echo(f"Supervisor started (PID {child_pid}).")
            return

        # Child: detach from terminal
        os.setsid()

    pid = os.getpid()
    save_pid(pid, pid_file)
    state = SupervisorState(
        pid=pid,
        start_time=now_iso(),
        last_heartbeat=now_iso(),
    )
    save_state(state, state_file)

    if foreground:
        typer.echo(f"Supervisor started in foreground (PID {pid}).")

    import logging

    from llm_rag.supervisor.loop import SupervisorAgent
    from llm_rag.supervisor.state import clear_pid
    from llm_rag.supervisor.watcher import InboxWatcher
    from llm_rag.utils.logging_config import configure_logging

    # Configure structured logging — JSON to file, colored to console in foreground
    log_file = settings.root_dir / ".supervisor" / "supervisor.log"
    configure_logging(
        log_file=log_file,
        level=logging.DEBUG if foreground else logging.INFO,
        foreground=foreground,
    )

    cli_logger = logging.getLogger("llm_rag.cli")

    shutdown_mgr = ShutdownManager()

    supervisor = SupervisorAgent(
        raw_dir=settings.raw_dir,
        settings=settings,
        interval_seconds=interval,
        supervisor_state=state,
        state_file=state_file,
        shutdown_manager=shutdown_mgr,
        pid_file=pid_file,
    )

    # Start inbox watcher
    inbox_path = settings.raw_dir / "inbox"
    inbox_path.mkdir(parents=True, exist_ok=True)
    watcher = InboxWatcher(inbox_path, supervisor.file_queue)
    watcher.start()

    # Start research scheduler if topics available
    if topics:
        try:
            from llm_rag.research.coordinator import ResearchAgent

            research_agent = ResearchAgent(settings)
            supervisor.start_scheduler(topics, sources_config, research_agent)
        except Exception:
            pass  # research agent may not be fully wired

    # Register signal handlers for graceful shutdown
    shutdown_mgr.register_signals()
    # Also handle SIGHUP for terminal disconnect
    signal.signal(signal.SIGHUP, shutdown_mgr._handle_signal)

    try:
        while not shutdown_mgr.is_shutting_down:
            # Update heartbeat
            state.last_heartbeat = now_iso()
            save_state(state, state_file)

            # Run one supervisor cycle
            try:
                asyncio.run(supervisor._run_cycle())
            except Exception:
                state.errors += 1

            if shutdown_mgr.is_shutting_down:
                break

            import time
            time.sleep(interval)
    finally:
        reason = shutdown_mgr.reason or ShutdownReason.MANUAL
        cli_logger.info("Initiating graceful shutdown (reason=%s)", reason.value)

        # Run graceful shutdown with a timeout
        try:
            asyncio.run(
                asyncio.wait_for(
                    supervisor.graceful_shutdown(reason),
                    timeout=ShutdownManager.SHUTDOWN_TIMEOUT,
                )
            )
        except (TimeoutError, asyncio.TimeoutError):
            cli_logger.warning("Shutdown timed out after %ss — forcing exit", ShutdownManager.SHUTDOWN_TIMEOUT)

        watcher.stop()
        # Ensure PID is cleared even if graceful_shutdown didn't do it
        clear_pid(pid_file)
        state.last_heartbeat = now_iso()
        save_state(state, state_file)
        shutdown_mgr.unregister_signals()
        cli_logger.info("Supervisor shut down cleanly")


@supervisor_app.command("stop")
def supervisor_stop() -> None:
    """Stop the running supervisor daemon."""
    from llm_rag.supervisor.state import (
        clear_pid,
        is_running,
        load_pid,
        send_stop_signal,
    )

    settings = get_settings()
    pid_file = settings.root_dir / ".supervisor" / "supervisor.pid"

    if not is_running(pid_file):
        typer.echo("Supervisor is not running.")
        raise SystemExit(1)

    pid = load_pid(pid_file)
    if send_stop_signal(pid_file):
        typer.echo(f"Sent stop signal to supervisor (PID {pid}).")
        clear_pid(pid_file)
    else:
        typer.echo("Failed to stop supervisor.")
        raise SystemExit(1)


@supervisor_app.command("status")
def supervisor_status() -> None:
    """Show supervisor running state and health."""
    from llm_rag.supervisor.state import HealthStatus, is_running, load_pid, load_state

    settings = get_settings()
    pid_file = settings.root_dir / ".supervisor" / "supervisor.pid"
    state_file = settings.root_dir / ".supervisor" / "state.json"

    running = is_running(pid_file)
    pid = load_pid(pid_file)
    state = load_state(state_file)

    _STATUS_BADGES = {
        HealthStatus.HEALTHY: "[HEALTHY]",
        HealthStatus.DEGRADED: "[DEGRADED]",
        HealthStatus.UNHEALTHY: "[UNHEALTHY]",
    }

    typer.echo("Supervisor Status")
    typer.echo("─" * 40)
    typer.echo(f"  Running:          {'yes' if running else 'no'}")
    typer.echo(f"  PID:              {pid or 'N/A'}")

    if state:
        health = state.health_status
        badge = _STATUS_BADGES[health]
        typer.echo(f"  Health:           {badge}")

        age = state.heartbeat_age()
        if age == float("inf"):
            age_str = "never"
        elif age < 60:
            age_str = f"{age:.0f}s ago"
        elif age < 3600:
            age_str = f"{age / 60:.1f}m ago"
        else:
            age_str = f"{age / 3600:.1f}h ago"
        typer.echo(f"  Heartbeat:        {age_str}")

        typer.echo(f"  Start time:       {state.start_time or 'N/A'}")
        typer.echo(f"  Last heartbeat:   {state.last_heartbeat or 'N/A'}")
        typer.echo(f"  Files processed:  {state.files_processed}")
        typer.echo(f"  Errors:           {state.errors}")
        typer.echo(f"  Error rate:       {state.error_rate:.1%}")
        if state.pending_files:
            typer.echo(f"  Pending files:    {len(state.pending_files)}")
            for f in state.pending_files[:10]:
                typer.echo(f"    - {f}")
        else:
            typer.echo("  Pending files:    0")

        if state.subagent_health:
            typer.echo("")
            typer.echo("Subagent Health")
            typer.echo("─" * 40)
            for name, sh in sorted(state.subagent_health.items()):
                sub_badge = _STATUS_BADGES[sh.status]
                typer.echo(f"  {name}:")
                typer.echo(f"    Status:       {sub_badge}")
                typer.echo(f"    Last run:     {sh.last_run or 'never'}")
                typer.echo(f"    Success rate: {sh.success_rate:.1%}")
                typer.echo(f"    Total runs:   {sh.total_runs}")
                typer.echo(f"    Failures:     {sh.consecutive_failures} consecutive")
    else:
        typer.echo("  No state file found.")
