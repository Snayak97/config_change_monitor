"""
Application configuration management via Pydantic BaseSettings.
Loads environment variables, validates settings, and provides typed access.
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Core Application
    app_name: str = "Config Change Monitoring System"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = "console"  # 'json' or 'console'

    # File Watcher
    watch_paths: List[str] = Field(default_factory=lambda: ["./sample_configs"])
    debounce_interval_seconds: float = 0.5
    max_read_retries: int = 3
    read_retry_delay_seconds: float = 0.1
    enable_hash_check: bool = True

    # Event Bus & Queue
    queue_max_size: int = 5000
    queue_worker_concurrency: int = 4

    # Webhook & Notifications
    webhook_url: Optional[str] = "http://localhost:8000/api/v1/test-webhook"
    webhook_timeout_seconds: float = 5.0
    webhook_secret: Optional[str] = "super-secret-signature-key"
    slack_webhook_url: Optional[str] = None

    # Retry & Circuit Breaker
    max_retries: int = 4
    retry_initial_delay_seconds: float = 1.0
    retry_backoff_multiplier: float = 2.0
    retry_max_delay_seconds: float = 30.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: float = 20.0

    # Storage & DLQ
    audit_db_path: str = "./audit_events.db"
    snapshot_cache_size: int = 2000
    dlq_max_size: int = 1000


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
