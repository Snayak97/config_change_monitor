"""
End-to-End Integration Tests:
- file change -> diff computation -> event bus -> webhook delivery
- Webhook payload contract validation
- Failure routing to Dead Letter Queue (DLQ) & replay
"""

import os
import json
import time
import asyncio
import pytest
from src.domain.models import ConfigChangeEvent, EventType
from src.bus.queue import AsyncEventQueue
from src.bus.event_bus import EventBus
from src.storage.audit_store import AuditStore
from src.storage.snapshot_cache import SnapshotCache
from src.notifier.dlq import DeadLetterQueue
from src.notifier.dispatcher import NotificationDispatcher
from src.notifier.targets import BaseNotifier
from src.watcher.file_watcher import FileWatcherService
from src.domain.exceptions import NotificationDispatchError


class MockWebhookTarget(BaseNotifier):
    """Mock webhook collecting delivered payloads for verification."""

    def __init__(self, name: str = "mock_webhook", should_fail: bool = False):
        self._name = name
        self.should_fail = should_fail
        self.delivered_events: list[ConfigChangeEvent] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def target_url(self) -> str:
        return "http://mock-webhook.local"

    async def send(self, event: ConfigChangeEvent) -> bool:
        if self.should_fail:
            raise NotificationDispatchError("Simulated 503 Service Unavailable")
        self.delivered_events.append(event)
        return True


def test_full_file_change_to_webhook_pipeline(temp_dir):
    """
    Integration test:
    1. Write initial configuration file
    2. Watch directory
    3. Modify configuration file on disk
    4. Verify structured event matches contract and reaches mock webhook target
    """
    async def _run():
        config_file = os.path.join(temp_dir, "app.json")
        initial_data = {"server": {"port": 8080}, "auth": {"enabled": True}}
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        # Initialize components
        event_bus = EventBus()
        queue = AsyncEventQueue()
        dlq = DeadLetterQueue()
        audit_db = os.path.join(temp_dir, "audit.db")
        audit_store = AuditStore(db_path=audit_db)
        snapshot_cache = SnapshotCache()

        mock_webhook = MockWebhookTarget(name="test_target")
        dispatcher = NotificationDispatcher(
            queue=queue,
            dlq=dlq,
            audit_store=audit_store,
            max_retries=2,
            base_delay=0.05
        )
        dispatcher.add_target(mock_webhook)

        # Wire event bus to queue and audit store
        async def _on_event(event: ConfigChangeEvent):
            audit_store.save_event(event)
            await queue.put(event)

        event_bus.subscribe(_on_event)

        # Start worker pool
        await dispatcher.start(concurrency=2)

        # Start file watcher with rapid debounce for test speed
        loop = asyncio.get_running_loop()
        watcher = FileWatcherService(
            event_bus=event_bus,
            snapshot_cache=snapshot_cache,
            debounce_interval=0.1,
            enable_hash_check=True
        )
        watcher.start(loop=loop)
        watcher.add_watch_path(temp_dir)

        try:
            # Allow baseline initialization
            await asyncio.sleep(0.1)

            # Mutate configuration file
            updated_data = {
                "server": {"port": 9090},          # updated
                "auth": {"enabled": True},         # unchanged
                "logging": {"level": "info"},      # added
            }
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(updated_data, f)

            # Wait for debouncing (0.1s) + worker processing
            await asyncio.sleep(0.35)

            # 1. Verify Webhook received the event
            assert len(mock_webhook.delivered_events) == 1
            delivered = mock_webhook.delivered_events[0]

            # 2. Contract Testing: Verify JSON schema compliance
            assert delivered.file == "app.json"
            assert delivered.changes.added == {"logging.level": "info"}
            assert delivered.changes.updated["server.port"].old == 8080
            assert delivered.changes.updated["server.port"].new == 9090
            assert delivered.changes.removed == {}
            assert delivered.changes.type_changes == {}

            # 3. Verify persistent audit log storage
            stored_events = audit_store.get_events()
            assert len(stored_events) == 1
            assert stored_events[0].id == delivered.id

        finally:
            watcher.stop()
            await dispatcher.stop()

    asyncio.run(_run())


def test_dlq_routing_on_target_failure():
    """
    Verify that when downstream service fails all retries,
    the event is safely routed to Dead Letter Queue and can be replayed.
    """
    async def _run():
        queue = AsyncEventQueue()
        dlq = DeadLetterQueue()
        mock_failing_target = MockWebhookTarget(name="failing_target", should_fail=True)

        dispatcher = NotificationDispatcher(
            queue=queue,
            dlq=dlq,
            max_retries=2,
            base_delay=0.02
        )
        dispatcher.add_target(mock_failing_target)

        await dispatcher.start(concurrency=1)

        try:
            from src.domain.models import ChangeSet
            test_event = ConfigChangeEvent(
                file="broken.yaml",
                changes=ChangeSet(added={"key": "val"})
            )

            await queue.put(test_event)
            # Wait for retries to exhaust
            await asyncio.sleep(0.2)

            # Verify routed to DLQ
            assert dlq.count() == 1
            records = dlq.list_records()
            assert records[0].event_id == test_event.id
            assert "Simulated 503" in records[0].last_error

            # Test Replay: fix target and replay
            mock_failing_target.should_fail = False
            replayed = await dispatcher.replay_dlq_record(records[0].id)
            assert replayed is True
            assert dlq.count() == 0  # Removed from DLQ after successful replay
            assert len(mock_failing_target.delivered_events) == 1

        finally:
            await dispatcher.stop()

    asyncio.run(_run())

