"""
Prometheus metrics collector and instrumentation for Configuration Change Monitoring.
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    REGISTRY
)

# Metric definitions
CHANGES_DETECTED_TOTAL = Counter(
    "config_changes_detected_total",
    "Total number of configuration changes detected",
    ["file", "event_type"]
)

KEYS_MUTATED_TOTAL = Counter(
    "config_keys_mutated_total",
    "Total count of specific keys altered",
    ["file", "category"]  # added, updated, removed, type_changes
)

NOTIFICATION_DISPATCHES_TOTAL = Counter(
    "config_notification_dispatches_total",
    "Total notification delivery attempts and results",
    ["target", "status"]  # status: success, failure, dead_letter
)

PROCESSING_LATENCY = Histogram(
    "config_change_processing_latency_seconds",
    "End-to-end processing latency from file detection to notification delivery",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

MONITORED_FILES_ACTIVE = Gauge(
    "config_monitored_files_active",
    "Current count of active monitored files"
)

DLQ_RECORDS_COUNT = Gauge(
    "config_dlq_records_count",
    "Current number of records held in the Dead Letter Queue"
)

CIRCUIT_BREAKER_STATE = Gauge(
    "config_circuit_breaker_state",
    "Current state of circuit breaker: 0 = CLOSED, 1 = HALF_OPEN, 2 = OPEN",
    ["target"]
)


def get_prometheus_metrics() -> tuple[bytes, str]:
    """Generate and return current Prometheus metrics scrape output."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
