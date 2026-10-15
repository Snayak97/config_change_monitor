"""
Asynchronous queue implementation providing backpressure, metrics, and buffering.
"""

import asyncio
from typing import Optional
from loguru import logger
from src.domain.models import ConfigChangeEvent


class AsyncEventQueue:
    """Asyncio-based queue with backpressure monitoring and size tracking."""

    def __init__(self, maxsize: int = 5000):
        self._queue: asyncio.Queue[ConfigChangeEvent] = asyncio.Queue(maxsize=maxsize)
        self.enqueued_count: int = 0
        self.dequeued_count: int = 0

    async def put(self, event: ConfigChangeEvent, timeout: Optional[float] = 2.0) -> bool:
        """Enqueue event with backpressure timeout."""
        try:
            if timeout:
                await asyncio.wait_for(self._queue.put(event), timeout=timeout)
            else:
                await self._queue.put(event)
            self.enqueued_count += 1
            return True
        except asyncio.TimeoutError:
            logger.error(
                f"Queue capacity exceeded ({self._queue.maxsize}). Dropping or backpressuring event {event.id}"
            )
            return False

    async def get(self) -> ConfigChangeEvent:
        """Dequeue event for worker processing."""
        event = await self._queue.get()
        self.dequeued_count += 1
        return event

    def task_done(self) -> None:
        self._queue.task_done()

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def is_empty(self) -> bool:
        return self._queue.empty()
