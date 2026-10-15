"""
FastAPI REST routes for Configuration Change Monitoring System.
"""

import os
import time
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from src.domain.models import ConfigChangeEvent, MonitoredFile, NotificationDeliveryRecord
from src.metrics.prometheus import get_prometheus_metrics

router = APIRouter()

# In-memory test webhook history for demonstration and verification
_test_webhook_history: List[Dict[str, Any]] = []
_start_time: float = time.time()


class WatchRequest(BaseModel):
    path: str = Field(..., description="Path to directory or file to monitor")


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    monitored_files_count: int
    queue_depth: int
    dlq_records_count: int
    circuit_breakers: Dict[str, Any]


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def get_health(request: Request):
    """System health check and diagnostic metrics."""
    app_state = request.app.state
    watcher_service = getattr(app_state, "watcher_service", None)
    dispatcher = getattr(app_state, "dispatcher", None)
    queue = getattr(app_state, "queue", None)
    dlq = getattr(app_state, "dlq", None)

    active_files = len(watcher_service.get_monitored_files()) if watcher_service else 0
    q_depth = queue.qsize if queue else 0
    dlq_count = dlq.count() if dlq else 0
    cb_statuses = dispatcher.get_circuit_breaker_statuses() if dispatcher else {}

    return HealthResponse(
        status="healthy",
        uptime_seconds=round(time.time() - _start_time, 2),
        monitored_files_count=active_files,
        queue_depth=q_depth,
        dlq_records_count=dlq_count,
        circuit_breakers=cb_statuses
    )


@router.get("/files", response_model=List[MonitoredFile], tags=["Management"])
async def list_monitored_files(request: Request):
    """Retrieve all files currently tracked and monitored by the system."""
    watcher = getattr(request.app.state, "watcher_service", None)
    if not watcher:
        return []
    return watcher.get_monitored_files()


@router.get("/events", response_model=List[ConfigChangeEvent], tags=["Management"])
async def list_recent_events(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    file: Optional[str] = Query(None, description="Optional file name filter")
):
    """Retrieve historical change events from persistent audit log."""
    store = getattr(request.app.state, "audit_store", None)
    if not store:
        return []
    return store.get_events(limit=limit, offset=offset, file_filter=file)


@router.post("/watch", status_code=status.HTTP_201_CREATED, tags=["Management"])
async def add_watch_path(body: WatchRequest, request: Request):
    """Add a file or directory path to real-time monitoring."""
    watcher = getattr(request.app.state, "watcher_service", None)
    if not watcher:
        raise HTTPException(status_code=500, detail="Watcher service not initialized")

    if not os.path.exists(body.path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target path '{body.path}' does not exist on disk"
        )

    success = watcher.add_watch_path(body.path)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to schedule watch on specified path")

    return {
        "message": f"Successfully registered watch path: {body.path}",
        "path": body.path,
        "is_directory": os.path.isdir(body.path)
    }


@router.delete("/watch/{file_path:path}", tags=["Management"])
async def remove_watch_path(file_path: str, request: Request):
    """Remove a file or directory from monitoring."""
    watcher = getattr(request.app.state, "watcher_service", None)
    if not watcher:
        raise HTTPException(status_code=500, detail="Watcher service not initialized")

    success = watcher.remove_watch_path(file_path)
    if not success:
        raise HTTPException(status_code=404, detail=f"Path '{file_path}' was not actively monitored")

    return {"message": f"Successfully removed watch path: {file_path}"}


@router.get("/metrics", tags=["Observability"])
async def prometheus_metrics():
    """Prometheus metrics endpoint for scraping."""
    content, content_type = get_prometheus_metrics()
    return Response(content=content, media_type=content_type)


# DLQ & Replay Endpoints
@router.get("/api/v1/dlq", response_model=List[NotificationDeliveryRecord], tags=["Reliability"])
async def list_dlq_records(request: Request, limit: int = 50):
    """List events currently held in Dead Letter Queue."""
    dlq = getattr(request.app.state, "dlq", None)
    if not dlq:
        return []
    return dlq.list_records(limit=limit)


@router.post("/api/v1/dlq/replay/{record_id}", tags=["Reliability"])
async def replay_dlq_record(record_id: str, request: Request):
    """Replay an undelivered notification from Dead Letter Queue."""
    dispatcher = getattr(request.app.state, "dispatcher", None)
    if not dispatcher:
        raise HTTPException(status_code=500, detail="Dispatcher service not available")

    success = await dispatcher.replay_dlq_record(record_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to replay DLQ record '{record_id}'. Check downstream status."
        )

    return {"status": "replayed", "record_id": record_id}


# Mock Webhook Endpoints for Testing & Verification
@router.post("/api/v1/test-webhook", tags=["Testing"])
async def test_webhook_receiver(request: Request):
    """
    Built-in test webhook target for effortless end-to-end testing.
    Captures incoming payloads and signature headers.
    """
    body = await request.json()
    headers = dict(request.headers)
    record = {
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "signature": headers.get("x-hub-signature-256"),
        "event_id": headers.get("x-event-id"),
        "payload": body
    }
    _test_webhook_history.insert(0, record)
    if len(_test_webhook_history) > 100:
        _test_webhook_history.pop()

    return {"status": "received", "event_id": record["event_id"]}


@router.get("/api/v1/test-webhook/history", tags=["Testing"])
async def get_test_webhook_history():
    """View events received by the built-in test webhook."""
    return _test_webhook_history


@router.post("/api/v1/simulate-change", tags=["Testing"])
async def simulate_change_action():
    """
    Simulate a genuine configuration mutation in sample_configs/config.yaml
    to test the entire pipeline end-to-end.
    """
    import yaml
    sample_file = os.path.abspath("./sample_configs/config.yaml")
    if not os.path.exists(sample_file):
        raise HTTPException(status_code=404, detail="sample_configs/config.yaml not found")

    with open(sample_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Mutate keys to demonstrate added, updated, and type change
    current_level = data.get("logging", {}).get("level", "info")
    new_level = "debug" if current_level == "info" else "info"
    if "logging" not in data:
        data["logging"] = {}
    data["logging"]["level"] = new_level

    # Update nested db host
    db_host = data.get("db", {}).get("host", "localhost")
    data["db"]["host"] = "prod-db" if db_host == "localhost" else "localhost"

    # Add dynamic timestamp
    data["lastSimulatedUpdate"] = time.strftime("%Y-%m-%d %H:%M:%S")

    with open(sample_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)

    return {
        "status": "success",
        "message": f"Updated logging.level to '{new_level}' and db.host in {sample_file}"
    }

