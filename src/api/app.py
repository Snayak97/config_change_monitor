"""
FastAPI Application Entry Point and Lifespan Manager.
Assembles the Hexagonal Architecture components: Watcher, Parsers, Engine, Queue, Notifier.
"""

import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.config import get_settings, Settings
from src.logger import setup_logging
from src.domain.models import ConfigChangeEvent
from src.storage.audit_store import AuditStore
from src.storage.snapshot_cache import default_snapshot_cache
from src.bus.queue import AsyncEventQueue
from src.bus.event_bus import default_event_bus
from src.notifier.dlq import default_dlq
from src.notifier.dispatcher import NotificationDispatcher
from src.notifier.targets import WebhookNotifier, SlackNotifier, ConsoleNotifier
from src.watcher.file_watcher import FileWatcherService
from src.api.routes import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager handling orchestrated startup and graceful shutdown."""
    settings = get_settings()
    setup_logging()
    logger.info(f"Initializing {settings.app_name} [{settings.app_env}]...")

    # 1. Initialize Storage & Queue
    audit_store = AuditStore(db_path=settings.audit_db_path)
    queue = AsyncEventQueue(maxsize=settings.queue_max_size)
    dlq = default_dlq

    # 2. Initialize Notification Dispatcher & Register Targets
    dispatcher = NotificationDispatcher(
        queue=queue,
        dlq=dlq,
        audit_store=audit_store,
        max_retries=settings.max_retries,
        base_delay=settings.retry_initial_delay_seconds,
        backoff_multiplier=settings.retry_backoff_multiplier,
        max_delay=settings.retry_max_delay_seconds,
        cb_failure_threshold=settings.circuit_breaker_failure_threshold,
        cb_recovery_timeout=settings.circuit_breaker_recovery_timeout_seconds
    )

    # Register Webhook target
    if settings.webhook_url:
        dispatcher.add_target(
            WebhookNotifier(
                url=settings.webhook_url,
                secret=settings.webhook_secret,
                timeout_seconds=settings.webhook_timeout_seconds,
                name="primary_webhook"
            )
        )

    # Register Slack target if configured
    if settings.slack_webhook_url:
        dispatcher.add_target(
            SlackNotifier(webhook_url=settings.slack_webhook_url, name="slack_alerts")
        )

    # Always register Console notifier for visibility
    dispatcher.add_target(ConsoleNotifier())

    # 3. Connect Event Bus Subscribers
    async def _on_change_event(event: ConfigChangeEvent):
        # Persist to audit store
        audit_store.save_event(event)
        # Enqueue for asynchronous reliable notification delivery
        await queue.put(event)

    default_event_bus.subscribe(_on_change_event)

    # 4. Start Dispatcher Async Worker Pool
    await dispatcher.start(concurrency=settings.queue_worker_concurrency)

    # 5. Initialize & Start File Watcher Service
    loop = asyncio.get_running_loop()
    watcher_service = FileWatcherService(
        event_bus=default_event_bus,
        snapshot_cache=default_snapshot_cache,
        debounce_interval=settings.debounce_interval_seconds,
        max_read_retries=settings.max_read_retries,
        read_retry_delay=settings.read_retry_delay_seconds,
        enable_hash_check=settings.enable_hash_check
    )
    watcher_service.start(loop=loop)

    # Add default watch paths
    for path in settings.watch_paths:
        if os.path.exists(path):
            watcher_service.add_watch_path(path)
        else:
            logger.warning(f"Configured watch path '{path}' does not exist on disk yet")

    # Store references on app state for dependency injection in endpoints
    app.state.settings = settings
    app.state.audit_store = audit_store
    app.state.queue = queue
    app.state.dlq = dlq
    app.state.dispatcher = dispatcher
    app.state.watcher_service = watcher_service

    logger.info("Application startup sequence completed successfully")
    yield

    # Graceful Shutdown
    logger.info("Initiating graceful shutdown...")
    watcher_service.stop()
    await dispatcher.stop()
    logger.info("Graceful shutdown completed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application instance."""
    app = FastAPI(
        title="Configuration Change Monitoring System",
        description="Production-ready system that detects changes in configuration files and reliably publishes structured events.",
        version="1.0.0",
        lifespan=lifespan
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Routes
    app.include_router(api_router)

    # Static Assets & Modern UI Dashboard
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        @app.get("/dashboard", include_in_schema=False)
        async def serve_dashboard():
            index_path = os.path.join(static_dir, "index.html")
            return FileResponse(index_path)

    return app


app = create_app()
