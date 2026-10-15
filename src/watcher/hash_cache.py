"""
Content-based hashing cache to prevent redundant diff calculations.
Uses SHA-256 checksums to identify genuine content mutations.
"""

import hashlib
from typing import Dict, Optional


class HashCache:
    """Thread-safe SHA-256 hash store for tracked files."""

    def __init__(self):
        self._hashes: Dict[str, str] = {}

    @staticmethod
    def calculate_hash(content: str) -> str:
        """Compute SHA-256 hexadecimal digest of string content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_hash(self, file_path: str) -> Optional[str]:
        return self._hashes.get(file_path)

    def set_hash(self, file_path: str, checksum: str) -> None:
        self._hashes[file_path] = checksum

    def remove_hash(self, file_path: str) -> None:
        self._hashes.pop(file_path, None)

    def has_content_changed(self, file_path: str, new_content: str) -> bool:
        """
        Check if new content differs from cached hash.
        Updates cache automatically if changed.
        """
        new_hash = self.calculate_hash(new_content)
        old_hash = self._hashes.get(file_path)
        if old_hash == new_hash:
            return False

        self._hashes[file_path] = new_hash
        return True

    def clear(self) -> None:
        self._hashes.clear()
