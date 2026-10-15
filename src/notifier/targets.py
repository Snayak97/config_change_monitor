"""
Notification targets: Webhook, Slack, and Console.
"""

from abc import ABC, abstractmethod
import hmac
import hashlib
import json
from typing import Optional, Dict, Any
import httpx
from loguru import logger
from src.domain.models import ConfigChangeEvent
from src.domain.exceptions import NotificationDispatchError


class BaseNotifier(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def target_url(self) -> str:
        pass

    @abstractmethod
    async def send(self, event: ConfigChangeEvent) -> bool:
        """Deliver the change event to target."""
        pass


class WebhookNotifier(BaseNotifier):
    """Production webhook target with optional HMAC-SHA256 signature."""

    def __init__(
        self,
        url: str,
        secret: Optional[str] = None,
        timeout_seconds: float = 5.0,
        name: str = "primary_webhook"
    ):
        self._name = name
        self._url = url
        self._secret = secret
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return self._name

    @property
    def target_url(self) -> str:
        return self._url

    def _generate_signature(self, payload_bytes: bytes) -> str:
        if not self._secret:
            return ""
        sig = hmac.new(self._secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    async def send(self, event: ConfigChangeEvent) -> bool:
        if not self._url:
            return False

        # Format payload to match required specification
        payload_dict = {
            "file": event.file,
            "timestamp": event.timestamp,
            "changes": event.changes.model_dump()
        }
        payload_bytes = json.dumps(payload_dict, indent=2).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ConfigChangeMonitor/1.0",
            "X-Event-ID": event.id,
            "X-Event-Type": event.event_type.value
        }
        if self._secret:
            headers["X-Hub-Signature-256"] = self._generate_signature(payload_bytes)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    self._url,
                    content=payload_bytes,
                    headers=headers
                )
                response.raise_for_status()
                logger.info(
                    f"[Webhook] Delivered event {event.id} ({event.file}) to {self._url} [Status: {response.status_code}]"
                )
                return True
            except httpx.HTTPStatusError as http_err:
                raise NotificationDispatchError(
                    f"Webhook target returned HTTP {http_err.response.status_code}: {http_err.response.text[:200]}"
                ) from http_err
            except httpx.RequestError as req_err:
                raise NotificationDispatchError(
                    f"Webhook network error connecting to {self._url}: {str(req_err)}"
                ) from req_err


class SlackNotifier(BaseNotifier):
    """Slack Incoming Webhook target with block formatting."""

    def __init__(self, webhook_url: str, name: str = "slack"):
        self._url = webhook_url
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def target_url(self) -> str:
        return self._url

    async def send(self, event: ConfigChangeEvent) -> bool:
        if not self._url:
            return False

        changes = event.changes
        summary_lines = []
        if changes.added:
            summary_lines.append(f"🟢 *Added ({len(changes.added)})*: " + ", ".join(f"`{k}`" for k in list(changes.added.keys())[:5]))
        if changes.updated:
            summary_lines.append(f"🟡 *Updated ({len(changes.updated)})*: " + ", ".join(f"`{k}`" for k in list(changes.updated.keys())[:5]))
        if changes.removed:
            summary_lines.append(f"🔴 *Removed ({len(changes.removed)})*: " + ", ".join(f"`{k}`" for k in list(changes.removed.keys())[:5]))
        if changes.type_changes:
            summary_lines.append(f"🟣 *Type Changes ({len(changes.type_changes)})*: " + ", ".join(f"`{k}`" for k in list(changes.type_changes.keys())[:5]))

        payload = {
            "text": f"Configuration updated: {event.file}",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🔔 Config Change Detected"}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*File:*\n`{event.file}`"},
                        {"type": "mrkdwn", "text": f"*Timestamp:*\n{event.timestamp}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(summary_lines) if summary_lines else "No specific key diffs."
                    }
                }
            ]
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.post(self._url, json=payload)
                resp.raise_for_status()
                return True
            except Exception as ex:
                raise NotificationDispatchError(f"Slack delivery failed: {str(ex)}") from ex


class ConsoleNotifier(BaseNotifier):
    """Outputs events to console log."""

    @property
    def name(self) -> str:
        return "console"

    @property
    def target_url(self) -> str:
        return "stdout"

    async def send(self, event: ConfigChangeEvent) -> bool:
        logger.info(
            f"[Notification-Console] Event {event.id} on {event.file} - "
            f"Added: {len(event.changes.added)}, Updated: {len(event.changes.updated)}, "
            f"Removed: {len(event.changes.removed)}, TypeChanges: {len(event.changes.type_changes)}"
        )
        return True
