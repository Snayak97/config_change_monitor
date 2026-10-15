"""
Resilient file reader handling partial writes, concurrent file locks,
and intermittent OS-level sharing violations.
"""

import os
import time
from typing import Optional
from loguru import logger
from src.domain.exceptions import FileReadError


class ResilientFileReader:
    """Reads file contents safely with retries and backoff for partial writes."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 0.1):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def read_file(self, file_path: str) -> str:
        """
        Read file contents with retry logic to tolerate atomic replace windows,
        intermittent locks, or in-flight writes.
        """
        if not os.path.exists(file_path):
            raise FileReadError(f"File not found: {file_path}")

        last_exception: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # Open with utf-8 encoding and replace fallback for decoding safety
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                # If file exists but is 0 bytes on the first attempt, wait a tiny bit
                # in case an editor is performing an atomic truncate-then-write
                if len(content) == 0 and attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    continue

                return content
            except (OSError, PermissionError, IOError) as ex:
                last_exception = ex
                logger.warning(
                    f"Transient read error on '{file_path}' (attempt {attempt}/{self.max_retries}): {ex}"
                )
                time.sleep(self.retry_delay * attempt)

        raise FileReadError(
            f"Failed to read file '{file_path}' after {self.max_retries} attempts: {last_exception}"
        ) from last_exception
