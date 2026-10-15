"""
SQLite persistent audit store for configuration change events and delivery records.
"""

import sqlite3
import json
from typing import List, Optional, Dict, Any
from loguru import logger
from src.domain.models import ConfigChangeEvent, NotificationDeliveryRecord, ChangeSet, EventType


class AuditStore:
    """Thread-safe SQLite storage for historical audit trail and replay."""

    def __init__(self, db_path: str = "./audit_events.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    file TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    changes_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_file ON events(file);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS delivery_records (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    last_attempt_at TEXT,
                    last_error TEXT,
                    event_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_delivery_status ON delivery_records(status);
            """)

    def save_event(self, event: ConfigChangeEvent) -> None:
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events (id, file, event_type, timestamp, changes_json, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.file,
                        event.event_type.value,
                        event.timestamp,
                        event.changes.model_dump_json(),
                        json.dumps(event.metadata)
                    )
                )
        except Exception as ex:
            logger.error(f"Failed to persist event {event.id} to SQLite: {ex}")

    def get_events(
        self,
        limit: int = 50,
        offset: int = 0,
        file_filter: Optional[str] = None
    ) -> List[ConfigChangeEvent]:
        with self._get_connection() as conn:
            if file_filter:
                cursor = conn.execute(
                    """
                    SELECT id, file, event_type, timestamp, changes_json, metadata_json
                    FROM events
                    WHERE file LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (f"%{file_filter}%", limit, offset)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, file, event_type, timestamp, changes_json, metadata_json
                    FROM events
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset)
                )

            events: List[ConfigChangeEvent] = []
            for row in cursor.fetchall():
                try:
                    changes_dict = json.loads(row["changes_json"])
                    metadata_dict = json.loads(row["metadata_json"])
                    events.append(ConfigChangeEvent(
                        id=row["id"],
                        file=row["file"],
                        event_type=EventType(row["event_type"]),
                        timestamp=row["timestamp"],
                        changes=ChangeSet(**changes_dict),
                        metadata=metadata_dict
                    ))
                except Exception as parse_err:
                    logger.warning(f"Failed to deserialize event row {row['id']}: {parse_err}")

            return events

    def get_event_by_id(self, event_id: str) -> Optional[ConfigChangeEvent]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, file, event_type, timestamp, changes_json, metadata_json FROM events WHERE id = ?",
                (event_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            changes_dict = json.loads(row["changes_json"])
            metadata_dict = json.loads(row["metadata_json"])
            return ConfigChangeEvent(
                id=row["id"],
                file=row["file"],
                event_type=EventType(row["event_type"]),
                timestamp=row["timestamp"],
                changes=ChangeSet(**changes_dict),
                metadata=metadata_dict
            )

    def count_events(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM events")
            return cursor.fetchone()[0]
