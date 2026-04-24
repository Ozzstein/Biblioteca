"""Tests for the llm-rag CLI shell."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import subprocess

import typer
from typer.testing import CliRunner

from llm_rag.cli import app
from llm_rag.query.agent import QueryResult

runner = CliRunner()


def test_app_is_typer_instance():
    assert isinstance(app, typer.Typer)


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "usage" in result.output.lower()
    assert "status" in result.output.lower()


def test_status_command_shows_config_summary():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Battery Research OS" in result.output
    assert "Root dir:" in result.output
    assert "Raw dir:" in result.output
    assert "Wiki dir:" in result.output
    assert "API Keys:" in result.output
    assert "ANTHROPIC_API_KEY:" in result.output
    assert "Models:" in result.output
    assert "Bulk extraction:" in result.output
    assert "Pipeline:" in result.output
    assert "Chunk size:" in result.output
    assert "Corpus:" in result.output
    assert "Raw files:" in result.output
    assert "Wiki pages:" in result.output


def test_ingest_help_exits_zero():
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "ingest" in result.output.lower()


def test_pipeline_help_exits_zero():
    result = runner.invoke(app, ["pipeline", "--help"])
    assert result.exit_code == 0
    assert "pipeline" in result.output.lower()


def test_ask_help_exits_zero():
    result = runner.invoke(app, ["ask", "--help"])
    assert result.exit_code == 0
    assert "ask" in result.output.lower() or "query" in result.output.lower()


@patch("llm_rag.cli.asyncio.run")
def test_ask_command_calls_query_agent(mock_asyncio_run):
    """ask command invokes QueryAgent and prints the result."""
    # asyncio.run will call the coroutine; we intercept it
    mock_result = QueryResult(answer="Test answer", sources=[])
    mock_asyncio_run.return_value = mock_result

    result = runner.invoke(app, ["ask", "test question"])
    assert result.exit_code == 0
    mock_asyncio_run.assert_called_once()


@patch("llm_rag.query.agent.QueryAgent.ask", new_callable=AsyncMock)
@patch("llm_rag.mcp.pool.MCPPool.__aexit__", new_callable=AsyncMock)
@patch("llm_rag.mcp.pool.MCPPool.__aenter__", new_callable=AsyncMock)
def test_ask_command_displays_answer_and_sources(mock_enter, mock_exit, mock_ask):
    """ask command displays the answer and sources from QueryAgent."""
    mock_enter.return_value = MagicMock()
    mock_ask.return_value = QueryResult(
        answer="LFP capacity fade is caused by SEI growth.",
        sources=["papers/lfp-001 §3.2", "papers/lfp-002 §1.1"],
    )

    result = runner.invoke(app, ["ask", "what causes LFP capacity fade?"])
    assert result.exit_code == 0
    assert "LFP capacity fade is caused by SEI growth." in result.output
    assert "## Sources" in result.output
    assert "- papers/lfp-001 §3.2" in result.output
    assert "- papers/lfp-002 §1.1" in result.output


@patch("llm_rag.query.agent.QueryAgent.ask", new_callable=AsyncMock)
@patch("llm_rag.mcp.pool.MCPPool.__aexit__", new_callable=AsyncMock)
@patch("llm_rag.mcp.pool.MCPPool.__aenter__", new_callable=AsyncMock)
def test_ask_command_no_sources(mock_enter, mock_exit, mock_ask):
    """ask command omits Sources section when there are none."""
    mock_enter.return_value = MagicMock()
    mock_ask.return_value = QueryResult(answer="No relevant information found.")

    result = runner.invoke(app, ["ask", "unknown topic"])
    assert result.exit_code == 0
    assert "No relevant information found." in result.output
    assert "## Sources" not in result.output


@patch("llm_rag.cli.asyncio.run", side_effect=RuntimeError("connection failed"))
def test_ask_command_error_exits_nonzero(mock_asyncio_run):
    """ask command prints error and exits 1 on failure."""
    result = runner.invoke(app, ["ask", "test"])
    assert result.exit_code == 1
    assert "Error: connection failed" in result.output


def test_console_script_entrypoint_resolves():
    """Smoke test: the console script 'llm-rag' installed by pyproject.toml resolves and runs."""
    result = subprocess.run(
        ["uv", "run", "--extra", "dev", "llm-rag", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0
    assert "status" in result.stdout.lower()


# --- Ingest command tests ---


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
def test_ingest_calls_pipeline_with_default_path(mock_run):
    """ingest with no args defaults to raw/inbox/."""
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code == 0
    assert "Ingesting" in result.output
    assert "Ingest complete" in result.output
    mock_run.assert_awaited_once()
    call_path = mock_run.call_args[0][0]
    assert str(call_path).endswith("raw/inbox")
    assert mock_run.call_args[1].get("force") is False


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
def test_ingest_with_path_option(mock_run):
    """ingest --path passes the resolved path to the runner."""
    result = runner.invoke(app, ["ingest", "--path", "/tmp/test-file.md"])
    assert result.exit_code == 0
    assert "Ingesting" in result.output
    mock_run.assert_awaited_once()
    call_path = mock_run.call_args[0][0]
    assert call_path == Path("/tmp/test-file.md")


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
def test_ingest_with_doc_id(mock_run, tmp_path):
    """ingest --doc-id resolves to a file under raw/."""
    # Create a file so the resolver can find it
    raw_dir = tmp_path / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    test_file = raw_dir / "test-paper.md"
    test_file.write_text("test content")

    with patch("llm_rag.cli.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.raw_dir = tmp_path / "raw"
        result = runner.invoke(app, ["ingest", "--doc-id", "papers/test-paper"])

    assert result.exit_code == 0
    mock_run.assert_awaited_once()
    call_path = mock_run.call_args[0][0]
    assert call_path == test_file


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
def test_ingest_with_force_flag(mock_run):
    """ingest --force passes force=True to the runner."""
    result = runner.invoke(app, ["ingest", "--force"])
    assert result.exit_code == 0
    assert mock_run.call_args[1].get("force") is True


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock, side_effect=RuntimeError("boom"))
def test_ingest_error_shows_message_and_exits_nonzero(mock_run):
    """ingest prints the error and exits with code 1 on failure."""
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code == 1
    assert "Error: boom" in result.output


# --- Pipeline run command tests ---


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
def test_pipeline_run_calls_pipeline(mock_run):
    """pipeline run with no args defaults to raw/inbox/."""
    result = runner.invoke(app, ["pipeline", "run"])
    assert result.exit_code == 0
    assert "Running pipeline" in result.output
    assert "Pipeline complete" in result.output
    mock_run.assert_awaited_once()


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
def test_pipeline_run_with_path(mock_run):
    """pipeline run --path passes path to the runner."""
    result = runner.invoke(app, ["pipeline", "run", "--path", "/tmp/doc.pdf"])
    assert result.exit_code == 0
    call_path = mock_run.call_args[0][0]
    assert call_path == Path("/tmp/doc.pdf")


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock)
def test_pipeline_run_with_force(mock_run):
    """pipeline run --force passes force=True."""
    result = runner.invoke(app, ["pipeline", "run", "--force"])
    assert result.exit_code == 0
    assert mock_run.call_args[1].get("force") is True


@patch("llm_rag.cli._run_pipeline", new_callable=AsyncMock, side_effect=RuntimeError("fail"))
def test_pipeline_run_error_exits_nonzero(mock_run):
    """pipeline run prints error and exits 1 on failure."""
    result = runner.invoke(app, ["pipeline", "run"])
    assert result.exit_code == 1
    assert "Error: fail" in result.output
