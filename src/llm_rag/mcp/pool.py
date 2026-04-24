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
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any

import anyio
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


DEFAULT_SERVERS: list[MCPServerConfig] = [
    MCPServerConfig("corpus-io", [sys.executable, "-m", "llm_rag.mcp.corpus_io"]),
    MCPServerConfig("wiki-io", [sys.executable, "-m", "llm_rag.mcp.wiki_io"]),
    MCPServerConfig("graph-io", [sys.executable, "-m", "llm_rag.mcp.graph_io"]),
]


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------


class MCPPool:
    """Async context manager that owns long-lived MCP server connections.

    Parameters
    ----------
    servers:
        List of server configs to start.  Defaults to ``DEFAULT_SERVERS``
        (corpus-io, wiki-io, graph-io).

    Examples
    --------
    ::

        async with MCPPool() as pool:
            session = pool.get("corpus-io")
            chunks = await session.call_tool("get_chunks", {"doc_id": "papers/x"})
    """

    def __init__(self, servers: list[MCPServerConfig] | None = None) -> None:
        self._configs: list[MCPServerConfig] = servers if servers is not None else DEFAULT_SERVERS
        self._sessions: dict[str, ClientSession] = {}
        self._cancel_scope: anyio.CancelScope | None = None
        self._outer_tg: TaskGroup | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_server(
        self,
        cfg: MCPServerConfig,
        ready_events: dict[str, anyio.Event],
    ) -> None:
        """Spawn one MCP server subprocess and keep it alive.

        Stores the initialised ``ClientSession`` in ``self._sessions`` and
        signals the corresponding ``anyio.Event`` once the MCP handshake
        completes.  Blocks until the pool's cancel scope is cancelled.
        """
        command, *args = cfg.command
        params = StdioServerParameters(command=command, args=args, env=cfg.env)

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logger.debug("MCP server %r connected", cfg.name)
                self._sessions[cfg.name] = session
                ready_events[cfg.name].set()
                # Stay alive until the pool's cancel scope is cancelled.
                await anyio.sleep_forever()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def configs(self) -> list[MCPServerConfig]:
        """Return the list of MCP server configurations.

        Returns
        -------
        list[MCPServerConfig]
            The server configs used to initialize this pool.
        """
        return self._configs

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> MCPPool:
        """Start all MCP server subprocesses and wait until they are ready.

        Implementation notes
        --------------------
        We enter an outer ``TaskGroup`` (stored on ``self._outer_tg``) and
        immediately start a single ``_supervised`` coroutine inside it.
        That coroutine opens an inner ``CancelScope`` (``self._cancel_scope``),
        spawns one server task per config, then waits for all of them to be
        ready before setting *all_ready*.  ``__aenter__`` returns as soon as
        *all_ready* is set; the server tasks remain running in the background.

        On ``__aexit__``, we cancel ``self._cancel_scope`` which unwinds every
        server task (closing sessions and subprocesses), then drain the outer
        task group.
        """
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
                    # Wait for every server to complete its MCP handshake.
                    for cfg in self._configs:
                        await ready_events[cfg.name].wait()
                    all_ready.set()
                    # Block here; cancelled by __aexit__ via self._cancel_scope.
                    await anyio.sleep_forever()

        # Enter the outer task group and start the supervised coroutine inside
        # it.  We keep the task group open (do not await it yet) so the server
        # tasks keep running after __aenter__ returns.
        self._outer_tg = anyio.create_task_group()
        await self._outer_tg.__aenter__()
        self._outer_tg.start_soon(_supervised)

        # Block until all servers have completed their MCP handshake.
        await all_ready.wait()
        return self

    async def __aexit__(self, *_: Any) -> None:
        """Shut down all MCP server subprocesses cleanly."""
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()

        if self._outer_tg is not None:
            # Drain the outer task group.  _supervised exits immediately
            # because the cancel scope is already cancelled.
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

        Parameters
        ----------
        name:
            Logical server name, e.g. ``"corpus-io"``.

        Returns
        -------
        mcp.ClientSession
            A fully initialised session.  Call ``session.call_tool(...)`` or
            ``session.list_tools()`` directly on this object.

        Raises
        ------
        KeyError
            If *name* is not a known server or the pool has not been entered.
        """
        if name not in self._sessions:
            known = list(self._sessions.keys())
            raise KeyError(
                f"No MCP server named {name!r}.  Known servers: {known}"
            )
        return self._sessions[name]
