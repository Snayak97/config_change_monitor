"""
Dead Letter Queue (DLQ) for capturing and replaying failed change notifications.
"""

from typing import List, Optional, Dict
from datetime import datetime, timezone
import threading
from loguru import logger
from src.domain.models import ConfigChangeEvent, NotificationDeliveryRecord, NotificationStatus


class DeadLetterQueue:
    """Manages undeliverable notifications with inspection and replay support."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._records: Dict[str, NotificationDeliveryRecord] = {}
        self._lock = threading.Lock()

    def add(
        self,
        event: ConfigChangeEvent,
        target_name: str,
        target_url: str,
        attempts: int,
        error_message: str
    ) -> NotificationDeliveryRecord:
        """Add a permanently failed notification to DLQ."""
        record = NotificationDeliveryRecord(
            event_id=event.id,
            target_name=target_name,
            target_url=target_url,
            event=event,
            attempt_count=attempts,
            status=NotificationStatus.DEAD_LETTER,
            last_attempt_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            last_error=error_message
        )

        with self._lock:
            if len(self._records) >= self.max_size:
                # Evict oldest entry
                oldest_id = next(iter(self._records))
                del self._records[oldest_id]
            self._records[record.id] = record

        logger.error(
            f"[DLQ] Enqueued event {event.id} ({event.file}) for target {target_name}. Reason: {error_message}"
        )
        return record

    def list_records(self, limit: int = 50) -> List[NotificationDeliveryRecord]:
        """Return list of current DLQ records."""
        with self._lock:
            return list(self._records.values())[-limit:]

    def get_record(self, record_id: str) -> Optional[NotificationDeliveryRecord]:
        with self._lock:
            return self._records.get(record_id)

    def remove(self, record_id: str) -> Optional[NotificationDeliveryRecord]:
        with self._lock:
            return self._records.pop(record_id, None)

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


# Global default DLQ
default_dlq = DeadLetterQueue()
