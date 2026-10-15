"""
File Watcher Service monitoring multi-format configuration files.
Integrates watchdog, debouncing, resilient reading, hash caching, and diff engine.
"""

import os
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from loguru import logger
from src.domain.models import (
    ConfigChangeEvent,
    EventType,
    FileFormat,
    MonitoredFile
)
from src.domain.exceptions import ParserError, FileReadError, UnsupportedFormatError
from src.parsers.factory import default_parser_factory, ParserFactory
from src.engine.diff_engine import DiffEngine, default_diff_engine
from src.watcher.debouncer import Debouncer
from src.watcher.hash_cache import HashCache
from src.watcher.reader import ResilientFileReader
from src.storage.snapshot_cache import SnapshotCache, default_snapshot_cache
from src.bus.event_bus import EventBus, default_event_bus
from src.metrics.prometheus import (
    CHANGES_DETECTED_TOTAL,
    KEYS_MUTATED_TOTAL,
    MONITORED_FILES_ACTIVE
)


class ConfigFileEventHandler(FileSystemEventHandler):
    """Dispatches raw OS file events into debounced processing pipeline."""

    def __init__(self, watcher_service: "FileWatcherService"):
        super().__init__()
        self.service = watcher_service

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.service.handle_os_event(event.src_path, EventType.MODIFIED)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.service.handle_os_event(event.src_path, EventType.CREATED)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.service.handle_os_event(event.src_path, EventType.DELETED)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.service.handle_os_event(event.src_path, EventType.DELETED)
            dest = getattr(event, "dest_path", None)
            if dest:
                self.service.handle_os_event(dest, EventType.CREATED)


class FileWatcherService:
    """Manages multi-file monitoring, debouncing, snapshotting, and change detection."""

    def __init__(
        self,
        event_bus: EventBus = default_event_bus,
        diff_engine: DiffEngine = default_diff_engine,
        snapshot_cache: SnapshotCache = default_snapshot_cache,
        parser_factory: ParserFactory = default_parser_factory,
        debounce_interval: float = 0.5,
        max_read_retries: int = 3,
        read_retry_delay: float = 0.1,
        enable_hash_check: bool = True
    ):
        self.event_bus = event_bus
        self.diff_engine = diff_engine
        self.snapshot_cache = snapshot_cache
        self.parser_factory = parser_factory
        self.enable_hash_check = enable_hash_check

        self.reader = ResilientFileReader(max_retries=max_read_retries, retry_delay=read_retry_delay)
        self.debouncer = Debouncer(debounce_interval_seconds=debounce_interval)
        self.hash_cache = HashCache()

        self._observer = Observer()
        self._handler = ConfigFileEventHandler(self)
        self._watched_paths: Dict[str, any] = {}  # path -> watch handle
        self._monitored_files: Dict[str, MonitoredFile] = {}  # canonical path -> MonitoredFile
        self._running: bool = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start file watcher thread and event processing."""
        if self._running:
            return
        self._loop = loop or asyncio.get_event_loop()
        self._observer.start()
        self._running = True
        logger.info("FileWatcherService background observer started")

    def stop(self) -> None:
        """Stop file watcher and cancel pending debounce timers."""
        if not self._running:
            return
        self._running = False
        self.debouncer.cancel_all()
        self._observer.stop()
        self._observer.join(timeout=5.0)
        logger.info("FileWatcherService observer stopped")

    def add_watch_path(self, path: str) -> bool:
        """Add a directory or individual file to monitoring."""
        abs_path = os.path.abspath(path)
        if abs_path in self._watched_paths:
            return True

        if not os.path.exists(abs_path):
            logger.warning(f"Watch path does not exist on disk: {abs_path}")
            return False

        if os.path.isdir(abs_path):
            # Watch entire directory recursively
            watch = self._observer.schedule(self._handler, abs_path, recursive=True)
            self._watched_paths[abs_path] = watch
            # Initialize snapshots for existing matching files
            for root, _, files in os.walk(abs_path):
                for f in files:
                    file_full_path = os.path.abspath(os.path.join(root, f))
                    self._register_and_snapshot_file(file_full_path)
        else:
            # Watch parent directory of single file
            parent_dir = os.path.dirname(abs_path)
            watch = self._observer.schedule(self._handler, parent_dir, recursive=False)
            self._watched_paths[abs_path] = watch
            self._register_and_snapshot_file(abs_path)

        MONITORED_FILES_ACTIVE.set(len(self._monitored_files))
        logger.info(f"Registered watch path: {abs_path}")
        return True

    def remove_watch_path(self, path: str) -> bool:
        """Unregister a monitored directory or file."""
        abs_path = os.path.abspath(path)
        watch = self._watched_paths.pop(abs_path, None)
        if watch:
            try:
                self._observer.unschedule(watch)
            except Exception as ex:
                logger.warning(f"Error unscheduling watch for {abs_path}: {ex}")

        # Remove tracked files matching this path
        to_remove = [k for k in self._monitored_files if k == abs_path or k.startswith(abs_path + os.sep)]
        for k in to_remove:
            self._monitored_files.pop(k, None)
            self.snapshot_cache.remove(k)
            self.hash_cache.remove_hash(k)
            self.debouncer.cancel(k)

        MONITORED_FILES_ACTIVE.set(len(self._monitored_files))
        logger.info(f"Removed watch path: {abs_path}")
        return True

    def _register_and_snapshot_file(self, file_path: str) -> None:
        """Initialize baseline snapshot for a detected configuration file."""
        fmt = self.parser_factory.get_format_for_path(file_path)
        if fmt == FileFormat.UNKNOWN:
            return  # Skip non-config files (.tmp, .git, etc.)

        try:
            content = self.reader.read_file(file_path)
            parser = self.parser_factory.get_parser_for_path(file_path)
            parsed_data = parser.parse(content)
            checksum = self.hash_cache.calculate_hash(content)

            self.hash_cache.set_hash(file_path, checksum)
            self.snapshot_cache.set(file_path, parsed_data)

            stat = os.stat(file_path)
            self._monitored_files[file_path] = MonitoredFile(
                path=os.path.basename(file_path),
                absolute_path=file_path,
                format=fmt,
                exists=True,
                size_bytes=stat.st_size,
                last_hash=checksum,
                last_modified_timestamp=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                status="active"
            )
            logger.debug(f"Initialized snapshot for: {file_path}")
        except Exception as ex:
            logger.warning(f"Could not load initial baseline for {file_path}: {ex}")
            self._monitored_files[file_path] = MonitoredFile(
                path=os.path.basename(file_path),
                absolute_path=file_path,
                format=fmt,
                exists=os.path.exists(file_path),
                status="error",
                last_error=str(ex)
            )

    def handle_os_event(self, raw_path: str, event_type: EventType) -> None:
        """Entry point called by FileSystemEventHandler from watchdog thread."""
        abs_path = os.path.abspath(raw_path)

        # Filter out non-configuration files
        fmt = self.parser_factory.get_format_for_path(abs_path)
        if fmt == FileFormat.UNKNOWN:
            return

        # Debounce the file modification/creation
        self.debouncer.debounce(
            key=abs_path,
            callback=self._process_file_event,
            file_path=abs_path,
            event_type=event_type,
            file_format=fmt
        )

    def _process_file_event(self, file_path: str, event_type: EventType, file_format: FileFormat) -> None:
        """Debounced callback executing file diff and event publication."""
        logger.debug(f"Processing debounced {event_type.value} event on {file_path}")

        # Handle File Deletion
        if event_type == EventType.DELETED or not os.path.exists(file_path):
            old_data = self.snapshot_cache.get(file_path)
            if old_data:
                change_event = self.diff_engine.create_change_event(
                    file_path=os.path.basename(file_path),
                    old_data=old_data,
                    new_data={},
                    event_type=EventType.DELETED
                )
                self.snapshot_cache.remove(file_path)
                self.hash_cache.remove_hash(file_path)
                if file_path in self._monitored_files:
                    self._monitored_files[file_path].exists = False
                    self._monitored_files[file_path].status = "deleted"
                self._dispatch_event_to_bus(change_event)
            return

        # Handle File Creation or Modification
        try:
            content = self.reader.read_file(file_path)
        except FileReadError as read_err:
            logger.error(f"Failed to read file {file_path}: {read_err}")
            if file_path in self._monitored_files:
                self._monitored_files[file_path].status = "error"
                self._monitored_files[file_path].last_error = str(read_err)
            return

        # Hash check: Avoid reprocessing if file content is unchanged
        if self.enable_hash_check and not self.hash_cache.has_content_changed(file_path, content):
            logger.debug(f"Ignoring event on {file_path}: content hash unchanged")
            return

        # Parse configuration
        try:
            parser = self.parser_factory.get_parser_for_path(file_path)
            new_data = parser.parse(content)
        except ParserError as parse_err:
            logger.warning(f"Syntax/Parse error in {file_path}: {parse_err}")
            if file_path in self._monitored_files:
                self._monitored_files[file_path].status = "invalid_syntax"
                self._monitored_files[file_path].last_error = str(parse_err)
            # Do NOT update snapshot; keep previous valid state
            return

        # Diff against last known snapshot
        old_data = self.snapshot_cache.get(file_path)
        effective_event_type = EventType.CREATED if old_data is None else EventType.MODIFIED

        change_event = self.diff_engine.create_change_event(
            file_path=os.path.basename(file_path),
            old_data=old_data,
            new_data=new_data,
            event_type=effective_event_type
        )

        # Update cache & file metadata
        self.snapshot_cache.set(file_path, new_data)
        checksum = self.hash_cache.calculate_hash(content)
        stat = os.stat(file_path)

        self._monitored_files[file_path] = MonitoredFile(
            path=os.path.basename(file_path),
            absolute_path=file_path,
            format=file_format,
            exists=True,
            size_bytes=stat.st_size,
            last_hash=checksum,
            last_modified_timestamp=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            status="active",
            last_error=None
        )

        # Only publish if genuine changes were detected
        if change_event.changes.has_changes:
            logger.info(
                f"Detected changes in {file_path}: "
                f"+{len(change_event.changes.added)} keys, "
                f"~{len(change_event.changes.updated)} keys, "
                f"-{len(change_event.changes.removed)} keys, "
                f"!{len(change_event.changes.type_changes)} type changes"
            )
            # Update Prometheus metrics
            CHANGES_DETECTED_TOTAL.labels(
                file=os.path.basename(file_path),
                event_type=effective_event_type.value
            ).inc()
            KEYS_MUTATED_TOTAL.labels(file=os.path.basename(file_path), category="added").inc(len(change_event.changes.added))
            KEYS_MUTATED_TOTAL.labels(file=os.path.basename(file_path), category="updated").inc(len(change_event.changes.updated))
            KEYS_MUTATED_TOTAL.labels(file=os.path.basename(file_path), category="removed").inc(len(change_event.changes.removed))
            KEYS_MUTATED_TOTAL.labels(file=os.path.basename(file_path), category="type_changes").inc(len(change_event.changes.type_changes))

            self._dispatch_event_to_bus(change_event)

    def _dispatch_event_to_bus(self, event: ConfigChangeEvent) -> None:
        """Safely bridge event from worker thread to asyncio event loop."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.event_bus.publish(event), self._loop)
        else:
            logger.warning(f"Asyncio loop unavailable to dispatch event {event.id}")

    def get_monitored_files(self) -> List[MonitoredFile]:
        """Return list of all currently tracked files."""
        return list(self._monitored_files.values())
