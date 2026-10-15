"""
Unit tests for event debouncing logic.
"""

import time
from src.watcher.debouncer import Debouncer


class TestDebouncer:
    def test_rapid_burst_calls_coalesce_into_single_execution(self):
        debouncer = Debouncer(debounce_interval_seconds=0.1)
        executions = []

        def callback(val):
            executions.append(val)

        # Trigger rapid bursts for the same key
        for i in range(5):
            debouncer.debounce("test_key", callback, i)
            time.sleep(0.02)  # Much shorter than 0.1s interval

        # Still within interval
        assert len(executions) == 0

        # Wait for debounce timer to fire
        time.sleep(0.15)
        # Should execute only once with the latest value (4)
        assert len(executions) == 1
        assert executions[0] == 4

    def test_cancellation(self):
        debouncer = Debouncer(debounce_interval_seconds=0.1)
        executions = []

        def callback():
            executions.append(True)

        debouncer.debounce("cancel_key", callback)
        debouncer.cancel("cancel_key")

        time.sleep(0.15)
        assert len(executions) == 0
