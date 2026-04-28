"""Structured JSON logging for the supervisor and pipeline."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# ANSI color codes for console output
_COLORS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[35m",  # magenta
    "RESET": "\033[0m",
}


class StructuredFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects for machine consumption."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        # Merge any extra structured fields attached via `extra={"event": ...}`
        for key in ("event", "source_name", "files_written", "error_detail",
                     "health_status", "reason", "duration_s", "doc_id"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry, default=str)


class ColorConsoleFormatter(logging.Formatter):
    """Human-friendly colored output for foreground / terminal use."""

    fmt_str = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self.fmt_str, datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def configure_logging(
    log_file: Path | None = None,
    level: int = logging.INFO,
    foreground: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 7,
) -> None:
    """Set up logging for the supervisor process.

    Args:
        log_file: Path to the JSON log file. If None, file logging is skipped.
        level: Root log level (DEBUG, INFO, WARNING, ERROR).
        foreground: If True, add a colored console handler to stderr.
        max_bytes: Max size per log file before rotation (default 10 MB).
        backup_count: Number of rotated log files to keep (default 7).
    """
    root = logging.getLogger("llm_rag")
    root.setLevel(level)

    # Remove any existing handlers to avoid duplicates on re-configure
    root.handlers.clear()

    # --- File handler (JSON structured) ---
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(StructuredFormatter())
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    # --- Console handler (colored, human-readable) ---
    if foreground:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(ColorConsoleFormatter())
        console_handler.setLevel(level)
        root.addHandler(console_handler)
