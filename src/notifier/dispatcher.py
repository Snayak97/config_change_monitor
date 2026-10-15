"""
Notification Dispatcher with worker pool, circuit breakers, and DLQ routing.
"""

import asyncio
import time
from typing import List, Dict, Optional
from loguru import logger
from src.domain.models import ConfigChangeEvent, NotificationDeliveryRecord, NotificationStatus
from src.notifier.targets import BaseNotifier, WebhookNotifier, SlackNotifier, ConsoleNotifier
from src.notifier.circuit_breaker import CircuitBreaker, CircuitState
from src.notifier.retry import retry_with_backoff
from src.notifier.dlq import DeadLetterQueue, default_dlq
from src.bus.queue import AsyncEventQueue
from src.storage.audit_store import AuditStore
from src.metrics.prometheus import (
    NOTIFICATION_DISPATCHES_TOTAL,
    PROCESSING_LATENCY,
    DLQ_RECORDS_COUNT,
    CIRCUIT_BREAKER_STATE
)


class NotificationDispatcher:
    """Orchestrates notification delivery across multiple targets with resilience."""

    def __init__(
        self,
        queue: AsyncEventQueue,
        dlq: DeadLetterQueue = default_dlq,
        audit_store: Optional[AuditStore] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        backoff_multiplier: float = 2.0,
        max_delay: float = 30.0,
        cb_failure_threshold: int = 5,
        cb_recovery_timeout: float = 20.0
    ):
        self.queue = queue
        self.dlq = dlq
        self.audit_store = audit_store
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff_multiplier = backoff_multiplier
        self.max_delay = max_delay

        self._targets: List[BaseNotifier] = []
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._cb_failure_threshold = cb_failure_threshold
        self._cb_recovery_timeout = cb_recovery_timeout

        self._worker_tasks: List[asyncio.Task] = []
        self._running: bool = False

    def add_target(self, target: BaseNotifier) -> None:
        """Register a notification target with an isolated circuit breaker."""
        self._targets.append(target)
        self._circuit_breakers[target.name] = CircuitBreaker(
            name=target.name,
            failure_threshold=self._cb_failure_threshold,
            recovery_timeout_seconds=self._cb_recovery_timeout
        )
        self._update_cb_metrics(target.name)

    def _update_cb_metrics(self, target_name: str) -> None:
        cb = self._circuit_breakers.get(target_name)
        if not cb:
            return
        state_val = 0
        if cb.state == CircuitState.HALF_OPEN:
            state_val = 1
        elif cb.state == CircuitState.OPEN:
            state_val = 2
        CIRCUIT_BREAKER_STATE.labels(target=target_name).set(state_val)

    async def start(self, concurrency: int = 4) -> None:
        """Start async consumer worker tasks."""
        if self._running:
            return
        self._running = True

        for i in range(concurrency):
            task = asyncio.create_task(self._worker_loop(worker_id=i))
            self._worker_tasks.append(task)
        logger.info(f"Notification Dispatcher started with {concurrency} workers")

    async def stop(self) -> None:
        """Gracefully stop worker tasks and finish in-flight jobs."""
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        logger.info("Notification Dispatcher workers stopped")

    async def _worker_loop(self, worker_id: int) -> None:
        while self._running:
            try:
                event = await self.queue.get()
                start_time = time.time()
                try:
                    await self._dispatch_to_targets(event)
                finally:
                    duration = time.time() - start_time
                    PROCESSING_LATENCY.observe(duration)
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.error(f"Worker {worker_id} unexpected error: {ex}")

    async def _dispatch_to_targets(self, event: ConfigChangeEvent) -> None:
        """Deliver change event to all configured notification targets."""
        for target in self._targets:
            cb = self._circuit_breakers[target.name]
            self._update_cb_metrics(target.name)

            # Check Circuit Breaker
            if not cb.can_execute():
                err_msg = f"Circuit breaker OPEN for target '{target.name}'. Refusing connection."
                logger.warning(err_msg)
                NOTIFICATION_DISPATCHES_TOTAL.labels(target=target.name, status="circuit_breaker_open").inc()
                self.dlq.add(
                    event=event,
                    target_name=target.name,
                    target_url=target.target_url,
                    attempts=0,
                    error_message=err_msg
                )
                DLQ_RECORDS_COUNT.set(self.dlq.count())
                continue

            # Execute with exponential backoff retry
            try:
                async def _send_wrapper():
                    return await target.send(event)

                await retry_with_backoff(
                    _send_wrapper,
                    max_retries=self.max_retries,
                    base_delay=self.base_delay,
                    multiplier=self.backoff_multiplier,
                    max_delay=self.max_delay,
                    operation_name=f"Notify-{target.name}"
                )

                cb.record_success()
                self._update_cb_metrics(target.name)
                NOTIFICATION_DISPATCHES_TOTAL.labels(target=target.name, status="success").inc()

            except Exception as ex:
                cb.record_failure(ex)
                self._update_cb_metrics(target.name)
                NOTIFICATION_DISPATCHES_TOTAL.labels(target=target.name, status="failure").inc()

                # Add to Dead Letter Queue
                self.dlq.add(
                    event=event,
                    target_name=target.name,
                    target_url=target.target_url,
                    attempts=self.max_retries,
                    error_message=str(ex)
                )
                DLQ_RECORDS_COUNT.set(self.dlq.count())

    async def replay_dlq_record(self, record_id: str) -> bool:
        """Attempt to redeliver an individual DLQ event."""
        record = self.dlq.get_record(record_id)
        if not record:
            return False

        # Find matching target
        matching_target = next((t for t in self._targets if t.name == record.target_name), None)
        if not matching_target:
            return False

        try:
            success = await matching_target.send(record.event)
            if success:
                self.dlq.remove(record_id)
                DLQ_RECORDS_COUNT.set(self.dlq.count())
                logger.info(f"[DLQ-Replay] Successfully redelivered DLQ event {record.event.id}")
                return True
        except Exception as ex:
            logger.error(f"[DLQ-Replay] Replay failed for record {record_id}: {ex}")

        return False

    def get_circuit_breaker_statuses(self) -> Dict[str, dict]:
        return {name: cb.to_dict() for name, cb in self._circuit_breakers.items()}
