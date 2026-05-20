"""
core/watcher.py -- File system watcher using watchdog.

Handles two events that matter for Downloads:
  - on_created: new file appears (e.g. drag-and-drop, save-as)
  - on_moved: browser finishes download and renames .crdownload -> real name

Both events go through the same stability check + processing pipeline.
Events are emitted via a Python callable (callback) to avoid a hard dependency
on PySide6 in this module, making it testable in isolation.

The callback signature: callback(path: str) -> None
"""

import logging
import threading
from pathlib import Path

from watchdog.observers import Observer  # type: ignore
from watchdog.events import (  # type: ignore
    FileSystemEventHandler,
    FileCreatedEvent,
    FileMovedEvent,
    DirCreatedEvent,
    DirMovedEvent,
)

from core.stability import is_transient

logger = logging.getLogger(__name__)


class _DownloadsHandler(FileSystemEventHandler):
    """
    Watchdog event handler that filters and forwards relevant file events
    to the provided callback.
    """

    def __init__(self, callback: callable) -> None:
        super().__init__()
        self._callback = callback

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            logger.info("Folder created: %s", event.src_path)
            self._dispatch(event.src_path)
            return
        path = event.src_path
        # Skip transient extensions -- the on_moved event will catch the final file.
        if is_transient(path):
            logger.debug("Skipping transient file: %s", path)
            return
        logger.info("File created: %s", path)
        self._dispatch(path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            logger.info("Folder renamed/moved to: %s", event.dest_path)
            self._dispatch(event.dest_path)
            return
        dest = event.dest_path
        # Only care about moves INTO (or within) the watch folder.
        # Skip if the final name is still transient.
        if is_transient(dest):
            return
        logger.info("File renamed/moved to: %s", dest)
        self._dispatch(dest)

    def _dispatch(self, path: str) -> None:
        """Run the callback in a daemon thread so the watchdog thread is never blocked."""
        t = threading.Thread(target=self._callback, args=(path,), daemon=True)
        t.start()


class FileWatcher:
    """
    Manages a watchdog Observer for a single directory.

    Usage:
        watcher = FileWatcher(folder_path, callback)
        watcher.start()
        ...
        watcher.stop()
    """

    def __init__(self, folder: str, callback: callable) -> None:
        self._folder = folder
        self._callback = callback
        self._observer: Observer | None = None

    @property
    def folder(self) -> str:
        return self._folder

    def start(self) -> None:
        if self._observer is not None:
            self.stop()
        self._observer = Observer()
        handler = _DownloadsHandler(self._callback)
        self._observer.schedule(handler, self._folder, recursive=False)
        self._observer.start()
        logger.info("Watching folder: %s", self._folder)

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("Stopped watching: %s", self._folder)

    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def change_folder(self, new_folder: str) -> None:
        """Restart the watcher on a different folder."""
        self._folder = new_folder
        if self.is_running():
            self.start()
