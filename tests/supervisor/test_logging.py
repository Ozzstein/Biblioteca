"""Tests for structured logging and observability."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from llm_rag.utils.logging_config import (
    ColorConsoleFormatter,
    StructuredFormatter,
    configure_logging,
)


class TestStructuredFormatter:
    """StructuredFormatter outputs valid single-line JSON."""

    def _make_record(self, message: str = "hello", level: int = logging.INFO, **extra: object) -> logging.LogRecord:
        record = logging.LogRecord(
            name="llm_rag.test",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=message,
            args=(),
            exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_basic_json_output(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record("test message")
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "llm_rag.test"
        assert "timestamp" in parsed

    def test_includes_extra_event_field(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record("start", event="supervisor_start")
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["event"] == "supervisor_start"

    def test_includes_extra_source_name(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record("sub", source_name="arxiv", files_written=5)
        parsed = json.loads(fmt.format(record))
        assert parsed["source_name"] == "arxiv"
        assert parsed["files_written"] == 5

    def test_includes_exception_info(self) -> None:
        fmt = StructuredFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="llm_rag.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )
        parsed = json.loads(fmt.format(record))
        assert "exception" in parsed
        assert "boom" in parsed["exception"]

    def test_output_is_single_line(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record("multi\nline\nmessage")
        output = fmt.format(record)
        # json.dumps puts \\n not actual newlines
        assert "\n" not in output

    def test_all_known_extra_fields(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record(
            "full",
            event="subagent_finish",
            source_name="pubmed",
            files_written=3,
            error_detail="timeout",
            health_status="degraded",
            reason="signal",
            duration_s=12.5,
            doc_id="papers/test-001",
        )
        parsed = json.loads(fmt.format(record))
        assert parsed["event"] == "subagent_finish"
        assert parsed["source_name"] == "pubmed"
        assert parsed["files_written"] == 3
        assert parsed["error_detail"] == "timeout"
        assert parsed["health_status"] == "degraded"
        assert parsed["reason"] == "signal"
        assert parsed["duration_s"] == 12.5
        assert parsed["doc_id"] == "papers/test-001"

    def test_missing_extra_fields_omitted(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record("plain")
        parsed = json.loads(fmt.format(record))
        assert "event" not in parsed
        assert "source_name" not in parsed


class TestColorConsoleFormatter:
    """ColorConsoleFormatter produces human-readable colored output."""

    def test_format_contains_level_and_message(self) -> None:
        fmt = ColorConsoleFormatter()
        record = logging.LogRecord(
            name="llm_rag.test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="something wrong",
            args=(),
            exc_info=None,
        )
        output = fmt.format(record)
        assert "something wrong" in output
        assert "WARNING" in output

    def test_format_contains_ansi_codes(self) -> None:
        fmt = ColorConsoleFormatter()
        record = logging.LogRecord(
            name="llm_rag.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="err",
            args=(),
            exc_info=None,
        )
        output = fmt.format(record)
        assert "\033[" in output  # contains ANSI escape


class TestConfigureLogging:
    """configure_logging sets up file and console handlers."""

    def test_file_handler_writes_json(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        configure_logging(log_file=log_file, level=logging.DEBUG, foreground=False)

        logger = logging.getLogger("llm_rag.test_file")
        logger.info("hello from test", extra={"event": "test_event"})

        # Flush handlers
        for h in logging.getLogger("llm_rag").handlers:
            h.flush()

        content = log_file.read_text()
        assert content.strip()
        parsed = json.loads(content.strip().split("\n")[-1])
        assert parsed["message"] == "hello from test"
        assert parsed["event"] == "test_event"

    def test_foreground_adds_console_handler(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        configure_logging(log_file=log_file, level=logging.INFO, foreground=True)

        root = logging.getLogger("llm_rag")
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "RotatingFileHandler" in handler_types
        assert "StreamHandler" in handler_types

    def test_no_file_handler_when_none(self) -> None:
        configure_logging(log_file=None, level=logging.INFO, foreground=True)

        root = logging.getLogger("llm_rag")
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "RotatingFileHandler" not in handler_types
        assert "StreamHandler" in handler_types

    def test_reconfigure_clears_old_handlers(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        configure_logging(log_file=log_file, level=logging.INFO, foreground=True)
        first_count = len(logging.getLogger("llm_rag").handlers)

        configure_logging(log_file=log_file, level=logging.INFO, foreground=True)
        second_count = len(logging.getLogger("llm_rag").handlers)

        assert first_count == second_count

    def test_log_file_parent_created(self, tmp_path: Path) -> None:
        log_file = tmp_path / "deep" / "nested" / "supervisor.log"
        configure_logging(log_file=log_file, level=logging.INFO)

        logger = logging.getLogger("llm_rag.test_nested")
        logger.info("nested test")
        for h in logging.getLogger("llm_rag").handlers:
            h.flush()

        assert log_file.exists()

    def test_debug_level_captured(self, tmp_path: Path) -> None:
        log_file = tmp_path / "debug.log"
        configure_logging(log_file=log_file, level=logging.DEBUG, foreground=False)

        logger = logging.getLogger("llm_rag.test_debug")
        logger.debug("debug message")
        for h in logging.getLogger("llm_rag").handlers:
            h.flush()

        content = log_file.read_text()
        parsed = json.loads(content.strip().split("\n")[-1])
        assert parsed["level"] == "DEBUG"
        assert parsed["message"] == "debug message"
