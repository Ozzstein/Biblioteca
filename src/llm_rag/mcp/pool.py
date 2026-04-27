"""MCPPool — long-lived async context manager that owns MCP server connections.

Usage::

    async with MCPPool() as pool:
        session = pool.get("corpus-io")   # mcp.ClientSession
        result = await session.call_tool("get_chunks", {"doc_id": "papers/foo"})

Each server is started as a subprocess via ``mcp.client.stdio.stdio_client``.
``pool.get(name)`` returns the initialised ``mcp.ClientSession`` for that server.

The pool keeps every subprocess alive for the duration of the ``async with`` block
and shuts everything down (stdin close → SIGTERM → SIGKILL escalation, as per the
MCP stdio shutdown spec) when the block exits.

Two extensions for the V2 lab-knowledge plan:

1. **YAML registry (CX4A)** — ``MCPPool.from_yaml(path)`` loads a federated
   source-server registry from ``config/mcp-sources.yaml``. The default
   ``MCPPool()`` constructor still uses ``DEFAULT_SERVERS`` for backward
   compatibility with existing pipeline / test code.

2. **Restart-on-crash with exponential backoff (A3A)** — when a source
   subprocess dies mid-session, the pool retries with backoff
   (1s, 2s, 4s, 8s) up to ``max_restarts`` times. After the cap is hit, the
   source is marked ``unavailable``; ``pool.get(name)`` raises
   ``SourceUnavailable``. This lets the gateway return degraded responses
   that name the missing source instead of 500-ing.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import yaml
from anyio.abc import TaskGroup
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server subprocess."""

    name: str
    """Logical name used to look up the connection with ``pool.get(name)``."""

    command: list[str]
    """Command + args to spawn the server, e.g. ``["python", "-m", "llm_rag.mcp.corpus_io"]``."""

    env: dict[str, str] | None = None
    """Optional extra environment variables to pass to the subprocess."""

    capabilities: list[str] = field(default_factory=list)
    """Optional capability strings declared by this source (federation v0.1)."""


DEFAULT_SERVERS: list[MCPServerConfig] = [
    MCPServerConfig("corpus-io", [sys.executable, "-m", "llm_rag.mcp.corpus_io"]),
    MCPServerConfig("wiki-io", [sys.executable, "-m", "llm_rag.mcp.wiki_io"]),
    MCPServerConfig("graph-io", [sys.executable, "-m", "llm_rag.mcp.graph_io"]),
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SourceUnavailable(KeyError):
    """Raised by ``pool.get(name)`` when a source is permanently unavailable.

    Subclass of ``KeyError`` so callers that already catch ``KeyError`` for
    "unknown server name" continue to work; new callers can catch this more
    specific type to distinguish "crashed past its retry budget" from
    "never registered."
    """


# ---------------------------------------------------------------------------
# YAML registry loader
# ---------------------------------------------------------------------------


_PROTOCOL_VERSION = "0.1"


def load_servers_from_yaml(path: Path | str) -> list[MCPServerConfig]:
    """Load source-server configs from ``config/mcp-sources.yaml``.

    Schema (v0.1)::

        protocol_version: "0.1"
        sources:
          - name: literature
            backend: stdio
            command: ["python", "-m", "llm_rag.mcp.sources.literature"]
            env:                       # optional
              FOO: "bar"
            capabilities:              # optional
              - "intent:reporting"

    HTTP backend support is reserved for the gateway's federation of remote
    sources (Step 4 + sister project) and not implemented here in Step 1.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If the document is malformed or the protocol version is unsupported.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"MCP sources registry not found: {path}")

    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level document must be a mapping")

    proto = data.get("protocol_version")
    if proto != _PROTOCOL_VERSION:
        raise ValueError(
            f"{path}: unsupported protocol_version {proto!r}; expected {_PROTOCOL_VERSION!r}"
        )

    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"{path}: 'sources' must be a non-empty list")

    configs: list[MCPServerConfig] = []
    seen: set[str] = set()
    for entry in sources:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: each source entry must be a mapping; got {entry!r}")

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{path}: source entry missing required 'name': {entry!r}")
        if name in seen:
            raise ValueError(f"{path}: duplicate source name {name!r}")
        seen.add(name)

        backend = entry.get("backend", "stdio")
        if backend != "stdio":
            raise ValueError(
                f"{path}: source {name!r} backend {backend!r} not supported in v{_PROTOCOL_VERSION}"
                " (only 'stdio' is implemented in Step 1)"
            )

        command = entry.get("command")
        if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
            raise ValueError(
                f"{path}: source {name!r} requires 'command' as a list of strings"
            )
        # Substitute "python" with the actual interpreter path so the spawned
        # subprocess uses the same env (uv venv, virtualenv) as the parent.
        if command and command[0] == "python":
            command = [sys.executable, *command[1:]]

        env_raw = entry.get("env")
        env: dict[str, str] | None
        if env_raw is None:
            env = None
        elif isinstance(env_raw, dict):
            env = {str(k): str(v) for k, v in env_raw.items()}
        else:
            raise ValueError(f"{path}: source {name!r} 'env' must be a mapping")

        capabilities = entry.get("capabilities", [])
        if not isinstance(capabilities, list) or not all(
            isinstance(c, str) for c in capabilities
        ):
            raise ValueError(
                f"{path}: source {name!r} 'capabilities' must be a list of strings"
            )

        configs.append(
            MCPServerConfig(name=name, command=command, env=env, capabilities=capabilities)
        )

    return configs


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------


_BACKOFF_SCHEDULE: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)
"""Per-attempt sleep before each restart attempt. Length determines max retries."""


class MCPPool:
    """Async context manager that owns long-lived MCP server connections.

    Parameters
    ----------
    servers:
        List of server configs to start. Defaults to ``DEFAULT_SERVERS``
        (corpus-io, wiki-io, graph-io) for backward compatibility with
        existing pipeline / test code.
    max_restarts:
        Per-server cap on subprocess restart attempts after a crash.
        Defaults to 5. Set to 0 to disable restart-on-crash entirely.

    Examples
    --------
    Default 3-server backward-compat layout::

        async with MCPPool() as pool:
            session = pool.get("corpus-io")
            chunks = await session.call_tool("get_chunks", {"doc_id": "papers/x"})

    Federated layout from YAML registry::

        async with MCPPool.from_yaml("config/mcp-sources.yaml") as pool:
            session = pool.get("literature")
            chunks = await session.call_tool("get_chunks", {"doc_id": "papers/x"})
    """

    def __init__(
        self,
        servers: list[MCPServerConfig] | None = None,
        *,
        max_restarts: int = 5,
    ) -> None:
        self._configs: list[MCPServerConfig] = (
            servers if servers is not None else DEFAULT_SERVERS
        )
        self._sessions: dict[str, ClientSession] = {}
        self._unavailable: dict[str, str] = {}  # name -> last error message
        self._max_restarts: int = max_restarts
        self._cancel_scope: anyio.CancelScope | None = None
        self._outer_tg: TaskGroup | None = None

    # ------------------------------------------------------------------
    # Alternative constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path | str, *, max_restarts: int = 5) -> MCPPool:
        """Construct a pool from a federation registry YAML file."""
        return cls(servers=load_servers_from_yaml(path), max_restarts=max_restarts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_server_once(
        self,
        cfg: MCPServerConfig,
        ready_event: anyio.Event,
    ) -> None:
        """Spawn one MCP server subprocess and keep it alive until cancellation.

        Stores the initialised ``ClientSession`` in ``self._sessions`` and
        signals ``ready_event`` once the MCP handshake completes. Returns
        normally on cancellation, raises any exception from subprocess
        startup or session lifetime.
        """
        command, *args = cfg.command
        params = StdioServerParameters(command=command, args=args, env=cfg.env)

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logger.debug("MCP server %r connected", cfg.name)
                self._sessions[cfg.name] = session
                ready_event.set()
                await anyio.sleep_forever()

    async def _run_server(
        self,
        cfg: MCPServerConfig,
        ready_events: dict[str, anyio.Event],
    ) -> None:
        """Run one server with restart-on-crash + exponential backoff (A3A).

        Pseudocode::

            for attempt in range(max_restarts + 1):
                try:
                    await _run_server_once(cfg, ready_event)
                    return                          # cancelled cleanly
                except Cancelled:
                    raise                           # pool shutting down
                except Exception:
                    if attempt == max_restarts: mark_unavailable(); return
                    sleep(backoff[attempt])
                    continue

        On every successful spawn, ``ready_events[cfg.name]`` is set so
        ``__aenter__`` proceeds. On respawn, the event is reused (already set
        from the first time, which is fine — callers only check it once).
        """
        ready_event = ready_events[cfg.name]
        attempt = 0
        while True:
            try:
                await self._run_server_once(cfg, ready_event)
                return  # normal cancellation path
            except (anyio.get_cancelled_exc_class(), KeyboardInterrupt):
                raise
            except Exception as exc:  # noqa: BLE001 -- intentional broad catch for restart
                # The session went away; remove it so callers can't accidentally
                # reuse a dead handle while we wait to restart.
                self._sessions.pop(cfg.name, None)

                if attempt >= self._max_restarts:
                    msg = f"crashed after {attempt + 1} attempts: {exc!r}"
                    self._unavailable[cfg.name] = msg
                    logger.warning(
                        "MCP source %r marked unavailable: %s", cfg.name, msg
                    )
                    # Make sure ready_event is set so __aenter__ doesn't hang
                    # on a never-ready source.
                    if not ready_event.is_set():
                        ready_event.set()
                    return

                delay = _BACKOFF_SCHEDULE[
                    min(attempt, len(_BACKOFF_SCHEDULE) - 1)
                ]
                logger.warning(
                    "MCP source %r crashed (attempt %d/%d): %r; restarting in %.1fs",
                    cfg.name,
                    attempt + 1,
                    self._max_restarts,
                    exc,
                    delay,
                )
                await anyio.sleep(delay)
                attempt += 1

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def configs(self) -> list[MCPServerConfig]:
        """Return the list of MCP server configurations."""
        return self._configs

    @property
    def unavailable(self) -> dict[str, str]:
        """Return a mapping of source-name → last-error for sources marked unavailable.

        Empty dict when no sources have crashed past their restart budget.
        Useful for the gateway to construct degraded-response warnings.
        """
        return dict(self._unavailable)

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> MCPPool:
        """Start all MCP server subprocesses and wait until they are ready."""
        all_ready: anyio.Event = anyio.Event()
        ready_events: dict[str, anyio.Event] = {
            cfg.name: anyio.Event() for cfg in self._configs
        }

        self._cancel_scope = anyio.CancelScope()

        async def _supervised() -> None:
            assert self._cancel_scope is not None
            with self._cancel_scope:
                async with anyio.create_task_group() as tg:
                    for cfg in self._configs:
                        tg.start_soon(self._run_server, cfg, ready_events)
                    # Wait for every server to complete its MCP handshake
                    # OR be marked unavailable (so we don't hang).
                    for cfg in self._configs:
                        await ready_events[cfg.name].wait()
                    all_ready.set()
                    await anyio.sleep_forever()

        self._outer_tg = anyio.create_task_group()
        await self._outer_tg.__aenter__()
        self._outer_tg.start_soon(_supervised)

        await all_ready.wait()
        return self

    async def __aexit__(self, *_: Any) -> None:
        """Shut down all MCP server subprocesses cleanly."""
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()

        if self._outer_tg is not None:
            try:
                await self._outer_tg.__aexit__(None, None, None)
            except Exception:
                logger.debug("MCPPool outer task group exit error (suppressed)", exc_info=True)

        self._sessions.clear()
        logger.debug("MCPPool shut down")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str) -> ClientSession:
        """Return the initialised ``ClientSession`` for the named MCP server.

        Raises
        ------
        SourceUnavailable
            If *name* was registered but its subprocess crashed past its
            restart budget. Inherits from ``KeyError`` for backward compat.
        KeyError
            If *name* is not a known server (never registered or pool not
            entered).
        """
        if name in self._unavailable:
            raise SourceUnavailable(
                f"MCP source {name!r} is unavailable: {self._unavailable[name]}"
            )
        if name not in self._sessions:
            known = list(self._sessions.keys())
            raise KeyError(
                f"No MCP server named {name!r}.  Known servers: {known}"
            )
        return self._sessions[name]
