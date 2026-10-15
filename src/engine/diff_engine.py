"""
Advanced Change Detection Engine.
Calculates structured diffs between configuration states, identifying:
- Added keys (with nested path support)
- Removed keys (with nested path support)
- Updated values (old vs new)
- Type changes (e.g., string -> object, integer -> string)
"""

from typing import Any, Dict, Optional
from src.domain.models import ChangeSet, ValueChange, TypeChange, ConfigChangeEvent, EventType
from src.engine.flattener import flatten_dict, get_type_name


class DiffEngine:
    """Computes structured differences between two configuration dictionaries."""

    def __init__(self, key_separator: str = "."):
        self.sep = key_separator

    def compute_diff(
        self,
        old_data: Optional[Dict[str, Any]],
        new_data: Optional[Dict[str, Any]]
    ) -> ChangeSet:
        """
        Compute differences between old_data and new_data.
        Handles None values safely (e.g. for created or deleted files).
        """
        old = old_data if old_data is not None else {}
        new = new_data if new_data is not None else {}

        added: Dict[str, Any] = {}
        updated: Dict[str, ValueChange] = {}
        removed: Dict[str, Any] = {}
        type_changes: Dict[str, TypeChange] = {}

        self._recursive_diff(
            old=old,
            new=new,
            prefix="",
            added=added,
            updated=updated,
            removed=removed,
            type_changes=type_changes
        )

        return ChangeSet(
            added=added,
            updated=updated,
            removed=removed,
            type_changes=type_changes
        )

    def _recursive_diff(
        self,
        old: Dict[str, Any],
        new: Dict[str, Any],
        prefix: str,
        added: Dict[str, Any],
        updated: Dict[str, ValueChange],
        removed: Dict[str, Any],
        type_changes: Dict[str, TypeChange]
    ) -> None:
        all_keys = set(old.keys()).union(set(new.keys()))

        for key in sorted(all_keys):
            full_key = f"{prefix}{self.sep}{key}" if prefix else str(key)
            in_old = key in old
            in_new = key in new

            # Case 1: Key only in new (Added)
            if in_new and not in_old:
                new_val = new[key]
                if isinstance(new_val, dict) and new_val:
                    # Flatten nested dictionary additions
                    flattened = flatten_dict(new_val, parent_key=full_key, sep=self.sep)
                    added.update(flattened)
                else:
                    added[full_key] = new_val
                continue

            # Case 2: Key only in old (Removed)
            if in_old and not in_new:
                old_val = old[key]
                if isinstance(old_val, dict) and old_val:
                    # Flatten nested dictionary removals
                    flattened = flatten_dict(old_val, parent_key=full_key, sep=self.sep)
                    removed.update(flattened)
                else:
                    removed[full_key] = old_val
                continue

            # Case 3: Key present in both (Check type and value)
            old_val = old[key]
            new_val = new[key]

            old_type = get_type_name(old_val)
            new_type = get_type_name(new_val)

            # Check for type change (e.g. string -> object, int -> string)
            if old_type != new_type:
                type_changes[full_key] = TypeChange(oldType=old_type, newType=new_type)
                continue

            # Both are dictionaries -> recurse
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                self._recursive_diff(
                    old=old_val,
                    new=new_val,
                    prefix=full_key,
                    added=added,
                    updated=updated,
                    removed=removed,
                    type_changes=type_changes
                )
                continue

            # Both are scalars or lists: check value equality
            if old_val != new_val:
                updated[full_key] = ValueChange(old=old_val, new=new_val)

    def create_change_event(
        self,
        file_path: str,
        old_data: Optional[Dict[str, Any]],
        new_data: Optional[Dict[str, Any]],
        event_type: EventType = EventType.MODIFIED
    ) -> ConfigChangeEvent:
        """Helper to generate a validated ConfigChangeEvent."""
        changes = self.compute_diff(old_data, new_data)
        return ConfigChangeEvent(
            file=file_path,
            event_type=event_type,
            changes=changes
        )


# Global default instance
default_diff_engine = DiffEngine()
