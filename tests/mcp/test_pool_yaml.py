"""Tests for the YAML registry loader (CX4A federation contract v0.1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from llm_rag.mcp.pool import (
    MCPPool,
    load_servers_from_yaml,
)

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_load_single_source(tmp_path: Path) -> None:
    yaml_text = """\
protocol_version: "0.1"
sources:
  - name: literature
    backend: stdio
    command: ["python", "-m", "llm_rag.mcp.sources.literature"]
    capabilities:
      - "intent:reporting"
"""
    path = tmp_path / "mcp-sources.yaml"
    path.write_text(yaml_text)

    configs = load_servers_from_yaml(path)
    assert len(configs) == 1
    cfg = configs[0]
    assert cfg.name == "literature"
    # "python" is rewritten to sys.executable so the subprocess uses the same env
    assert cfg.command[0] == sys.executable
    assert cfg.command[1:] == ["-m", "llm_rag.mcp.sources.literature"]
    assert cfg.capabilities == ["intent:reporting"]
    assert cfg.env is None


def test_load_multiple_sources_with_env(tmp_path: Path) -> None:
    yaml_text = """\
protocol_version: "0.1"
sources:
  - name: literature
    backend: stdio
    command: ["python", "-m", "llm_rag.mcp.sources.literature"]
  - name: lab
    backend: stdio
    command: ["python", "-m", "llm_rag.mcp.sources.lab"]
    env:
      LAB_DEBUG: "1"
    capabilities:
      - "tag:sop"
      - "tag:meeting"
"""
    path = tmp_path / "mcp-sources.yaml"
    path.write_text(yaml_text)

    configs = load_servers_from_yaml(path)
    assert [c.name for c in configs] == ["literature", "lab"]
    assert configs[1].env == {"LAB_DEBUG": "1"}
    assert configs[1].capabilities == ["tag:sop", "tag:meeting"]


def test_command_passthrough_when_not_python(tmp_path: Path) -> None:
    """A non-'python' command should pass through unchanged (no sys.executable rewrite)."""
    yaml_text = """\
protocol_version: "0.1"
sources:
  - name: external-tool
    backend: stdio
    command: ["/usr/bin/env", "node", "server.js"]
"""
    path = tmp_path / "mcp-sources.yaml"
    path.write_text(yaml_text)

    configs = load_servers_from_yaml(path)
    assert configs[0].command == ["/usr/bin/env", "node", "server.js"]


def test_from_yaml_alt_constructor(tmp_path: Path) -> None:
    yaml_text = """\
protocol_version: "0.1"
sources:
  - name: literature
    backend: stdio
    command: ["python", "-m", "llm_rag.mcp.sources.literature"]
"""
    path = tmp_path / "mcp-sources.yaml"
    path.write_text(yaml_text)

    pool = MCPPool.from_yaml(path)
    assert [c.name for c in pool.configs] == ["literature"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_servers_from_yaml(tmp_path / "nope.yaml")


def test_unsupported_protocol_version(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text('protocol_version: "9.0"\nsources: []\n')
    with pytest.raises(ValueError, match="unsupported protocol_version"):
        load_servers_from_yaml(path)


def test_empty_sources_list(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text('protocol_version: "0.1"\nsources: []\n')
    with pytest.raises(ValueError, match="non-empty list"):
        load_servers_from_yaml(path)


def test_duplicate_source_names(tmp_path: Path) -> None:
    yaml_text = """\
protocol_version: "0.1"
sources:
  - name: literature
    backend: stdio
    command: ["python", "-m", "x"]
  - name: literature
    backend: stdio
    command: ["python", "-m", "y"]
"""
    path = tmp_path / "x.yaml"
    path.write_text(yaml_text)
    with pytest.raises(ValueError, match="duplicate source name"):
        load_servers_from_yaml(path)


def test_unsupported_backend(tmp_path: Path) -> None:
    yaml_text = """\
protocol_version: "0.1"
sources:
  - name: future
    backend: http
    url: "https://example.com/mcp"
"""
    path = tmp_path / "x.yaml"
    path.write_text(yaml_text)
    with pytest.raises(ValueError, match="not supported in v0.1"):
        load_servers_from_yaml(path)


def test_missing_command(tmp_path: Path) -> None:
    yaml_text = """\
protocol_version: "0.1"
sources:
  - name: bad
    backend: stdio
"""
    path = tmp_path / "x.yaml"
    path.write_text(yaml_text)
    with pytest.raises(ValueError, match="requires 'command'"):
        load_servers_from_yaml(path)


# ---------------------------------------------------------------------------
# Real registry sanity check
# ---------------------------------------------------------------------------


def test_repo_registry_loads() -> None:
    """The committed config/mcp-sources.yaml in this repo must always parse."""
    from llm_rag.config import PROJECT_ROOT

    registry_path = PROJECT_ROOT / "config" / "mcp-sources.yaml"
    if not registry_path.exists():
        pytest.skip("config/mcp-sources.yaml not present in this checkout")
    configs = load_servers_from_yaml(registry_path)
    assert any(c.name == "literature" for c in configs), (
        "literature source must be present in the registry"
    )
