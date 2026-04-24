from __future__ import annotations

import queue
from pathlib import Path

from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileModifiedEvent

from llm_rag.supervisor.watcher import WATCHED_EXTENSIONS, InboxWatcher


def _make_watcher(tmp_path: Path) -> tuple[InboxWatcher, queue.Queue[Path]]:
    q: queue.Queue[Path] = queue.Queue()
    return InboxWatcher(watch_path=tmp_path, file_queue=q), q


def test_on_created_pdf_enqueued(tmp_path: Path) -> None:
    watcher, q = _make_watcher(tmp_path)
    event = FileCreatedEvent(str(tmp_path / "paper.pdf"))
    watcher.on_created(event)
    assert not q.empty()
    assert q.get() == tmp_path / "paper.pdf"


def test_on_created_md_enqueued(tmp_path: Path) -> None:
    watcher, q = _make_watcher(tmp_path)
    event = FileCreatedEvent(str(tmp_path / "note.md"))
    watcher.on_created(event)
    assert q.get() == tmp_path / "note.md"


def test_on_created_directory_skipped(tmp_path: Path) -> None:
    watcher, q = _make_watcher(tmp_path)
    event = DirCreatedEvent(str(tmp_path / "subdir"))
    watcher.on_created(event)
    assert q.empty()


def test_on_created_unknown_extension_skipped(tmp_path: Path) -> None:
    watcher, q = _make_watcher(tmp_path)
    event = FileCreatedEvent(str(tmp_path / "data.xyz"))
    watcher.on_created(event)
    assert q.empty()


def test_on_modified_md_enqueued(tmp_path: Path) -> None:
    watcher, q = _make_watcher(tmp_path)
    event = FileModifiedEvent(str(tmp_path / "notes.md"))
    watcher.on_modified(event)
    assert q.get() == tmp_path / "notes.md"


def test_watched_extensions_set() -> None:
    assert ".pdf" in WATCHED_EXTENSIONS
    assert ".md" in WATCHED_EXTENSIONS
    assert ".csv" in WATCHED_EXTENSIONS
    assert ".txt" in WATCHED_EXTENSIONS
