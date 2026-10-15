"""
Unit tests for Advanced Change Detection Engine.
Verifies added, removed, updated, nested, and type-change classifications.
"""

from src.engine.diff_engine import DiffEngine
from src.domain.models import EventType


class TestDiffEngine:
    def setup_method(self):
        self.engine = DiffEngine()

    def test_added_keys_flat_and_nested(self):
        old = {"server": {"port": 80}}
        new = {
            "server": {"port": 80},
            "logging": {"level": "debug"},
            "debug": True
        }
        changes = self.engine.compute_diff(old, new)
        assert changes.added == {
            "logging.level": "debug",
            "debug": True
        }
        assert changes.updated == {}
        assert changes.removed == {}
        assert changes.type_changes == {}

    def test_removed_keys_flat_and_nested(self):
        old = {
            "cache": {"enabled": True, "ttl": 3600},
            "obsolete": "value"
        }
        new = {}
        changes = self.engine.compute_diff(old, new)
        assert changes.removed == {
            "cache.enabled": True,
            "cache.ttl": 3600,
            "obsolete": "value"
        }
        assert changes.added == {}

    def test_updated_values(self):
        old = {"db": {"host": "localhost", "port": 5432}}
        new = {"db": {"host": "prod-db", "port": 5432}}
        changes = self.engine.compute_diff(old, new)
        assert "db.host" in changes.updated
        assert changes.updated["db.host"].old == "localhost"
        assert changes.updated["db.host"].new == "prod-db"
        assert "db.port" not in changes.updated

    def test_type_changes(self):
        old = {
            "featureFlags": "v1_basic",
            "retries": 5
        }
        new = {
            "featureFlags": {"v2": True},
            "retries": "5"
        }
        changes = self.engine.compute_diff(old, new)
        assert "featureFlags" in changes.type_changes
        assert changes.type_changes["featureFlags"].oldType == "string"
        assert changes.type_changes["featureFlags"].newType == "object"

        assert "retries" in changes.type_changes
        assert changes.type_changes["retries"].oldType == "integer"
        assert changes.type_changes["retries"].newType == "string"

    def test_assignment_specification_example(self):
        """
        Verify exact match with the assignment requirement example:
        {
          "file": "config.yaml",
          "timestamp": "...",
          "changes": {
            "added": { "logging.level": "debug" },
            "updated": { "db.host": { "old": "localhost", "new": "prod-db" } },
            "removed": { "cache.enabled": true },
            "type_changes": { "featureFlags": { "oldType": "string", "newType": "object" } }
          }
        }
        """
        old = {
            "db": {"host": "localhost"},
            "cache": {"enabled": True},
            "featureFlags": "string_flag"
        }
        new = {
            "db": {"host": "prod-db"},
            "logging": {"level": "debug"},
            "featureFlags": {"enabled": True}
        }
        event = self.engine.create_change_event(
            file_path="config.yaml",
            old_data=old,
            new_data=new,
            event_type=EventType.MODIFIED
        )

        assert event.file == "config.yaml"
        assert event.changes.added == {"logging.level": "debug"}
        assert event.changes.removed == {"cache.enabled": True}
        assert event.changes.updated["db.host"].old == "localhost"
        assert event.changes.updated["db.host"].new == "prod-db"
        assert event.changes.type_changes["featureFlags"].oldType == "string"
        assert event.changes.type_changes["featureFlags"].newType == "object"
