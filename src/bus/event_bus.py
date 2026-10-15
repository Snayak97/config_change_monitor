"""
Event Bus for asynchronous publish/subscribe decoupling.
"""

import asyncio
from typing import Callable, List, Coroutine, Any
from loguru import logger
from src.domain.models import ConfigChangeEvent


class EventBus:
    """Central event bus connecting watchers, stores, metrics, and notifiers."""

    def __init__(self):
        self._handlers: List[Callable[[ConfigChangeEvent], Coroutine[Any, Any, None]]] = []

    def subscribe(self, handler: Callable[[ConfigChangeEvent], Coroutine[Any, Any, None]]) -> None:
        """Register an async subscriber handler."""
        self._handlers.append(handler)

    async def publish(self, event: ConfigChangeEvent) -> None:
        """Publish event concurrently to all registered subscribers."""
        if not self._handlers:
            logger.warning(f"No subscribers registered for event {event.id}")
            return

        tasks = [asyncio.create_task(self._safe_execute(handler, event)) for handler in self._handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _safe_execute(
        handler: Callable[[ConfigChangeEvent], Coroutine[Any, Any, None]],
        event: ConfigChangeEvent
    ) -> None:
        try:
            await handler(event)
        except Exception as ex:
            logger.exception(f"Unhandled exception in event handler {handler.__name__}: {ex}")


# Global EventBus instance
default_event_bus = EventBus()
