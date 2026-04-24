"""Retry decorator with exponential backoff for transient failures."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Exception types considered transient (worth retrying).
TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    OSError,
)


def is_transient(exc: BaseException) -> bool:
    """Return True if the exception is considered transient."""
    if isinstance(exc, TRANSIENT_EXCEPTIONS):
        return True
    # Also treat RuntimeError with "rate" or "timeout" in the message as transient.
    if isinstance(exc, RuntimeError):
        msg = str(exc).lower()
        if "rate" in msg or "timeout" in msg or "overloaded" in msg:
            return True
    return False


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    transient_check: Callable[[BaseException], bool] = is_transient,
) -> Callable[[F], F]:
    """Decorator that retries an async function with exponential backoff.

    Parameters
    ----------
    max_attempts:
        Total number of attempts (including the first). Must be >= 1.
    base_delay:
        Initial delay in seconds before the first retry.
    max_delay:
        Maximum delay cap in seconds.
    transient_check:
        Callable that returns True if an exception is transient and worth retrying.
        Non-transient exceptions are raised immediately.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if not transient_check(exc):
                        raise
                    if attempt == max_attempts:
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning(
                        "Attempt %d/%d for %s failed (%s: %s), retrying in %.1fs",
                        attempt,
                        max_attempts,
                        fn.__qualname__,
                        type(exc).__name__,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
            # Should not reach here, but satisfy type checker
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
