from __future__ import annotations

import queue
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

WATCHED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".md", ".txt", ".csv"})


class InboxWatcher(FileSystemEventHandler):
    def __init__(self, watch_path: Path, file_queue: queue.Queue[Path]) -> None:
        super().__init__()
        self._watch_path = watch_path
        self._queue = file_queue
        self._observer = Observer()

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        path = Path(str(event.src_path))
        if not event.is_directory and path.suffix in WATCHED_EXTENSIONS:
            self._queue.put(path)

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        path = Path(str(event.src_path))
        if not event.is_directory and path.suffix in WATCHED_EXTENSIONS:
            self._queue.put(path)

    def start(self) -> None:
        self._observer.schedule(self, str(self._watch_path), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
