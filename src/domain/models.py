"""
Domain models for the Configuration Change Monitoring System.
Defines immutable data structures, diff formats, and event payloads.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
import uuid


class EventType(str, Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


class FileFormat(str, Enum):
    JSON = "json"
    YAML = "yaml"
    ENV = "env"
    PROPERTIES = "properties"
    UNKNOWN = "unknown"


class ValueChange(BaseModel):
    old: Any
    new: Any


class TypeChange(BaseModel):
    oldType: str
    newType: str


class ChangeSet(BaseModel):
    added: Dict[str, Any] = Field(default_factory=dict)
    updated: Dict[str, ValueChange] = Field(default_factory=dict)
    removed: Dict[str, Any] = Field(default_factory=dict)
    type_changes: Dict[str, TypeChange] = Field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.type_changes)

    @property
    def total_changes_count(self) -> int:
        return len(self.added) + len(self.updated) + len(self.removed) + len(self.type_changes)


class ConfigChangeEvent(BaseModel):
    """
    Standardized change event payload matching the specification format:
    {
      "file": "config.yaml",
      "timestamp": "2026-05-13T10:30:00Z",
      "changes": {
        "added": { "logging.level": "debug" },
        "updated": { "db.host": { "old": "localhost", "new": "prod-db" } },
        "removed": { "cache.enabled": true },
        "type_changes": { "featureFlags": { "oldType": "string", "newType": "object" } }
      }
    }
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file: str
    event_type: EventType = EventType.MODIFIED
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    changes: ChangeSet
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    RETRYING = "retrying"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class NotificationDeliveryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str
    target_name: str
    target_url: str
    event: ConfigChangeEvent
    attempt_count: int = 0
    status: NotificationStatus = NotificationStatus.PENDING
    last_attempt_at: Optional[str] = None
    last_error: Optional[str] = None
    next_retry_at: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )


class MonitoredFile(BaseModel):
    path: str
    absolute_path: str
    format: FileFormat
    exists: bool = True
    size_bytes: int = 0
    last_hash: Optional[str] = None
    last_modified_timestamp: Optional[str] = None
    status: str = "active"  # "active", "error", "deleted"
    last_error: Optional[str] = None
