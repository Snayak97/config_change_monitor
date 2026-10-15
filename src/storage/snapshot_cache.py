"""
In-memory cache of configuration snapshots (parsed dictionaries).
Maintains last known valid states to calculate accurate diffs.
"""

from typing import Any, Dict, Optional
import threading


class SnapshotCache:
    """Thread-safe cache storing parsed configuration dictionaries per file path."""

    def __init__(self, max_size: int = 2000):
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.max_size = max_size

    def get(self, file_path: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            val = self._snapshots.get(file_path)
            return dict(val) if val is not None else None

    def set(self, file_path: str, data: Dict[str, Any]) -> None:
        with self._lock:
            # Simple eviction if exceeding max_size
            if len(self._snapshots) >= self.max_size and file_path not in self._snapshots:
                first_key = next(iter(self._snapshots))
                del self._snapshots[first_key]
            self._snapshots[file_path] = dict(data)

    def remove(self, file_path: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._snapshots.pop(file_path, None)

    def has(self, file_path: str) -> bool:
        with self._lock:
            return file_path in self._snapshots

    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()


# Global snapshot cache
default_snapshot_cache = SnapshotCache()
