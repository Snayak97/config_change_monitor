"""
Thread-safe and asyncio-compatible debouncer to coalesce rapid burst events
into a single consolidated trigger per file path.
"""

import threading
import time
from typing import Callable, Dict, Any
from loguru import logger


class Debouncer:
    """
    Debounces rapid events per key (e.g. file path).
    Ensures that if multiple events occur within the debounce_interval window,
    only the latest invocation executes after inactivity.
    """

    def __init__(self, debounce_interval_seconds: float = 0.5):
        self.interval = debounce_interval_seconds
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def debounce(self, key: str, callback: Callable[..., Any], *args, **kwargs) -> None:
        """Schedule callback execution for key, resetting any pending timer."""
        with self._lock:
            if key in self._timers:
                self._timers[key].cancel()

            def _wrapper():
                with self._lock:
                    self._timers.pop(key, None)
                try:
                    callback(*args, **kwargs)
                except Exception as ex:
                    logger.error(f"Error executing debounced callback for '{key}': {ex}")

            timer = threading.Timer(self.interval, _wrapper)
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def cancel(self, key: str) -> None:
        """Cancel pending debounce timer for key."""
        with self._lock:
            if key in self._timers:
                self._timers[key].cancel()
                del self._timers[key]

    def cancel_all(self) -> None:
        """Cancel all pending timers during shutdown."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
