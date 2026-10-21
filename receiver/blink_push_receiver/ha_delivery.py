from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .capture import EVENTS_NAME, _append_private, utc_now


DELIVERABLE_CLASSIFICATIONS = {"doorbell_press", "camera_motion"}


def delivery_key(record: dict[str, Any]) -> str:
    fcm = record.get("fcm") or {}
    payload = record.get("payload") or {}
    identity = (
        fcm.get("persistent_id")
        or fcm.get("id")
        or payload.get("unique_id")
        or record.get("received_at")
        or json.dumps(record, sort_keys=True, separators=(",", ":"))
    )
    return hashlib.sha256(str(identity).encode("utf-8")).hexdigest()


def _provider_timestamp(provider_sent_ms: Any) -> str | None:
    try:
        value = float(provider_sent_ms) / 1000
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def build_ha_event(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") or {}
    return {
        "schema_version": 1,
        "source": "blink_push_receiver",
        "event_id": delivery_key(record),
        "classification": record.get("classification"),
        "category": payload.get("category"),
        "event_type": payload.get("event_type"),
        "camera_name": payload.get("camera_name"),
        "provider_timestamp": _provider_timestamp(record.get("provider_sent_ms")),
        "created_at": payload.get("created_at"),
        "received_at": record.get("received_at"),
    }


class HomeAssistantWebhook:
    """Send sanitized Blink events to a local Home Assistant webhook."""

    def __init__(self, url: str, timeout_seconds: float = 5) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or "/api/webhook/" not in parsed.path
        ):
            raise ValueError("Home Assistant webhook URL is invalid")
        self.url = url
        self.timeout_seconds = timeout_seconds

    def send(self, event: dict[str, Any]) -> None:
        body = json.dumps(event, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise OSError(f"Home Assistant returned HTTP {response.status}")


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return records


def initialize_delivery_checkpoint(data_dir: Path) -> bool:
    """Skip events captured before HA forwarding was first enabled."""
    path = data_dir / EVENTS_NAME
    records = _load_records(path)
    if any(record.get("kind") == "ha_webhook_initialized" for record in records):
        return False
    existing_keys = {
        delivery_key(record)
        for record in records
        if record.get("kind") == "fcm_message"
        and record.get("classification") in DELIVERABLE_CLASSIFICATIONS
    }
    _append_private(path, {
        "kind": "ha_webhook_initialized",
        "received_at": utc_now(),
        "existing_event_count": len(existing_keys),
        "existing_delivery_keys": sorted(existing_keys),
    })
    return True


def deliver_pending_once(data_dir: Path, webhook: HomeAssistantWebhook) -> tuple[int, int]:
    """Deliver persisted events and remember successful posts for restart-safe retries."""
    path = data_dir / EVENTS_NAME
    records = _load_records(path)
    if initialize_delivery_checkpoint(data_dir):
        return 0, 0

    delivered = {
        str(record.get("delivery_key"))
        for record in records
        if record.get("kind") == "ha_webhook_sent" and record.get("delivery_key")
    }
    for record in records:
        if record.get("kind") == "ha_webhook_initialized":
            delivered.update(
                str(key)
                for key in record.get("existing_delivery_keys", [])
                if key
            )
    sent = 0
    failed = 0
    for record in records:
        if record.get("kind") != "fcm_message":
            continue
        if record.get("classification") not in DELIVERABLE_CLASSIFICATIONS:
            continue
        key = delivery_key(record)
        if key in delivered:
            continue
        try:
            webhook.send(build_ha_event(record))
        except (HTTPError, URLError, OSError, ValueError, TimeoutError):
            failed += 1
            continue
        _append_private(path, {
            "kind": "ha_webhook_sent",
            "received_at": utc_now(),
            "delivery_key": key,
        })
        delivered.add(key)
        sent += 1
    return sent, failed


def run_delivery_worker(
    data_dir: Path,
    webhook_url: str,
    stop_event: threading.Event,
    wake_event: threading.Event,
) -> None:
    try:
        webhook = HomeAssistantWebhook(webhook_url)
    except ValueError:
        print("Home Assistant webhook URL is invalid; forwarding is disabled", flush=True)
        return

    print("Home Assistant webhook forwarding enabled", flush=True)
    while not stop_event.is_set():
        wake_event.clear()
        sent, failed = deliver_pending_once(data_dir, webhook)
        if sent:
            print(f"Forwarded {sent} Blink event(s) to Home Assistant", flush=True)
        if failed:
            print("Home Assistant webhook delivery failed; will retry", flush=True)
            wake_event.wait(5)
        else:
            wake_event.wait()


def webhook_url_from_environment() -> str:
    return os.environ.get("BLINK_PUSH_HA_WEBHOOK_URL", "").strip()
