"""
Interactive Change Test Cases Runner for Configuration Change Monitoring System.
Demonstrates:
  1. Value Updates (old -> new)
  2. Key Additions (+added)
  3. Key Removals (-removed)
  4. Type Changes (!string -> object)
  5. Multi-format support (.yaml, .json, .env, .properties)
"""

import sys
import os
import json

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.engine.diff_engine import DiffEngine
from src.parsers.yaml_parser import YamlConfigParser
from src.parsers.json_parser import JsonConfigParser
from src.parsers.env_parser import EnvConfigParser
from src.parsers.properties_parser import PropertiesConfigParser
from src.domain.models import EventType


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f" 🧪 {title}")
    print("=" * 70)


def print_diff_result(changes):
    print("\nComputed Diff Output:")
    if changes.added:
        print("  🟢 ADDED:")
        for k, v in changes.added.items():
            print(f"     + {k}: {json.dumps(v)}")
    if changes.updated:
        print("  🟡 UPDATED:")
        for k, v in changes.updated.items():
            print(f"     ~ {k}: old={json.dumps(v.old)} -> new={json.dumps(v.new)}")
    if changes.removed:
        print("  🔴 REMOVED:")
        for k, v in changes.removed.items():
            print(f"     - {k}: {json.dumps(v)}")
    if changes.type_changes:
        print("  🟣 TYPE CHANGES:")
        for k, v in changes.type_changes.items():
            print(f"     ! {k}: {v.oldType} -> {v.newType}")


def main():
    engine = DiffEngine()

    # -------------------------------------------------------------
    # Test Case 1: Value Updates (YAML)
    # -------------------------------------------------------------
    print_banner("Test Case 1: Value Updates in YAML (db.host and server.port)")
    old_yaml = {
        "server": {"host": "0.0.0.0", "port": 8080},
        "db": {"host": "localhost", "port": 5432}
    }
    new_yaml = {
        "server": {"host": "0.0.0.0", "port": 9000},       # updated port
        "db": {"host": "prod-cluster.internal", "port": 5432} # updated host
    }
    changes1 = engine.compute_diff(old_yaml, new_yaml)
    print_diff_result(changes1)

    # -------------------------------------------------------------
    # Test Case 2: Key Additions & Removals (JSON)
    # -------------------------------------------------------------
    print_banner("Test Case 2: Added & Removed Keys in JSON")
    old_json = {
        "service": "payment-api",
        "cache": {"enabled": True, "ttl": 3600}, # will be removed
        "limits": {"ratePerMinute": 1000}
    }
    new_json = {
        "service": "payment-api",
        "limits": {"ratePerMinute": 1000},
        "security": {"require2FA": True, "jwtExpiry": 7200} # added
    }
    changes2 = engine.compute_diff(old_json, new_json)
    print_diff_result(changes2)

    # -------------------------------------------------------------
    # Test Case 3: Type Changes (string -> object, int -> string)
    # -------------------------------------------------------------
    print_banner("Test Case 3: Type Mutations (string -> object, boolean -> string)")
    old_types = {
        "featureFlags": "v1_basic",
        "maintenanceMode": True
    }
    new_types = {
        "featureFlags": {"v2": True, "canaryPercent": 20}, # string -> object
        "maintenanceMode": "scheduled_for_midnight"        # boolean -> string
    }
    changes3 = engine.compute_diff(old_types, new_types)
    print_diff_result(changes3)

    # -------------------------------------------------------------
    # Test Case 4: Exact Assignment Specification Example
    # -------------------------------------------------------------
    print_banner("Test Case 4: Assignment Specification Example Event")
    old_spec = {
        "db": {"host": "localhost"},
        "cache": {"enabled": True},
        "featureFlags": "v1_basic"
    }
    new_spec = {
        "logging": {"level": "debug"},
        "db": {"host": "prod-db"},
        "featureFlags": {"v2": True}
    }
    event = engine.create_change_event(
        file_path="config.yaml",
        old_data=old_spec,
        new_data=new_spec,
        event_type=EventType.MODIFIED
    )
    print("\nFull Event JSON matching assignment spec:")
    print(event.model_dump_json(indent=2))

    # -------------------------------------------------------------
    # Test Case 5: .env Key-Value Mutations
    # -------------------------------------------------------------
    print_banner("Test Case 5: .env File Configuration Changes")
    env_parser = EnvConfigParser()
    raw_env_old = "DEBUG=false\nPORT=8000\nAPI_KEY=key_123"
    raw_env_new = "DEBUG=true\nPORT=9090\nAPI_KEY=key_123\nNEW_FEATURE=enabled"
    changes_env = engine.compute_diff(env_parser.parse(raw_env_old), env_parser.parse(raw_env_new))
    print_diff_result(changes_env)

    # -------------------------------------------------------------
    # Test Case 6: Java .properties Mutations
    # -------------------------------------------------------------
    print_banner("Test Case 6: Java .properties File Changes")
    prop_parser = PropertiesConfigParser()
    raw_prop_old = "server.port=8080\nspring.application.name=orders"
    raw_prop_new = "server.port=9090\nspring.application.name=orders\nmanagement.endpoints.enabled=true"
    changes_prop = engine.compute_diff(prop_parser.parse(raw_prop_old), prop_parser.parse(raw_prop_new))
    print_diff_result(changes_prop)

    print("\n" + "=" * 70)
    print(" ✅ All 6 Change Test Cases Evaluated Successfully!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
