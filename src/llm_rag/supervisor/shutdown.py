"""Graceful shutdown manager for the supervisor process."""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from enum import Enum

logger = logging.getLogger(__name__)


class ShutdownReason(str, Enum):
    """Why the supervisor is shutting down."""

    SIGTERM = "SIGTERM"
    SIGINT = "SIGINT"
    SIGHUP = "SIGHUP"
    TIMEOUT = "timeout"
    MANUAL = "manual"


class ShutdownManager:
    """Coordinates graceful shutdown of the supervisor process.

    Registers signal handlers for SIGTERM, SIGINT, and SIGHUP.
    Exposes an ``is_shutting_down`` flag and an asyncio Event that
    async code can await.
    """

    SHUTDOWN_TIMEOUT = 30.0  # seconds

    def __init__(self) -> None:
        self._shutting_down = False
        self._reason: ShutdownReason | None = None
        self._event = threading.Event()
        self._async_event: asyncio.Event | None = None
        self._original_handlers: dict[int, object] = {}

    # -- properties ----------------------------------------------------------

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    @property
    def reason(self) -> ShutdownReason | None:
        return self._reason

    @property
    def shutdown_event(self) -> threading.Event:
        """Thread-safe event that is set when shutdown is requested."""
        return self._event

    def get_async_event(self, loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Event:
        """Return (or create) an asyncio.Event bound to the current loop."""
        if self._async_event is None:
            self._async_event = asyncio.Event()
        return self._async_event

    # -- signal registration -------------------------------------------------

    def register_signals(self) -> None:
        """Install signal handlers for SIGTERM, SIGINT, SIGHUP."""
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            self._original_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, self._handle_signal)

    def unregister_signals(self) -> None:
        """Restore original signal handlers."""
        for sig, handler in self._original_handlers.items():
            signal.signal(sig, handler)
        self._original_handlers.clear()

    # -- trigger -------------------------------------------------------------

    def request_shutdown(self, reason: ShutdownReason) -> None:
        """Initiate shutdown (can be called from signal handler or code)."""
        if self._shutting_down:
            return  # already shutting down
        self._shutting_down = True
        self._reason = reason
        self._event.set()
        if self._async_event is not None:
            self._async_event.set()
        logger.info("Shutdown requested: %s", reason.value)

    # -- internal ------------------------------------------------------------

    def _handle_signal(self, signum: int, frame: object) -> None:
        sig_map = {
            signal.SIGTERM: ShutdownReason.SIGTERM,
            signal.SIGINT: ShutdownReason.SIGINT,
            signal.SIGHUP: ShutdownReason.SIGHUP,
        }
        reason = sig_map.get(signum, ShutdownReason.MANUAL)
        self.request_shutdown(reason)
