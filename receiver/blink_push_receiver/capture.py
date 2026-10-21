from __future__ import annotations

import base64
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..vendor.fcm_receiver.messages_manual import DataMessageStanza
from .blink_account import BlinkAccountError, acknowledge_notification
from .state import atomic_json, ensure_private_dir, read_json


EVENTS_NAME = "messages.ndjson"
MOTION_TYPES = {"cloud_motion", "cam2sm_motion"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _merge_json_fields(fields: dict[str, str]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in ("data", "payload", "message", "notification"):
        value = fields.get(key)
        if not value:
            continue
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            merged.update(parsed)
    merged.update(fields)
    return merged


def payload_fields(message: DataMessageStanza) -> dict[str, Any]:
    app_fields: dict[str, str] = {}
    for item in message.app_data:
        app_fields[item.key] = item.value
    payload = _merge_json_fields(app_fields)
    if message.category and "category" not in payload:
        payload["category"] = message.category
    if message.raw_data:
        try:
            raw_value = json.loads(message.raw_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raw_value = None
        if isinstance(raw_value, dict):
            payload = {**raw_value, **payload}
    return payload


def classify(payload: dict[str, Any]) -> str:
    category = str(payload.get("category", "")).lower()
    event_type = str(payload.get("event_type", "")).lower()
    if category == "media" and event_type == "button_press":
        return "doorbell_press"
    if category == "motion" and event_type in MOTION_TYPES:
        return "camera_motion"
    return "unclassified"


def _append_private(path: Path, record: dict[str, Any]) -> None:
    ensure_private_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)
        data = (json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n").encode()
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


class MessageCapture:
    """Privately persist MCS messages, Blink fields, and event timestamps."""

    def __init__(self, data_dir: Path, on_event: Callable[[], None] | None = None) -> None:
        self.data_dir = data_dir
        self.state_path = data_dir / "fcm-state.json"
        self.events_path = data_dir / EVENTS_NAME
        self.on_event = on_event
        self._lock = threading.RLock()
        ensure_private_dir(data_dir)

    def handle(self, message: DataMessageStanza, client: Any) -> None:
        received_at = utc_now()
        payload = payload_fields(message)
        event_type = classify(payload)
        persistent_id = message.persistent_id

        record = {
            "kind": "fcm_message",
            "received_at": received_at,
            "classification": event_type,
            "provider_sent_ms": message.sent,
            "provider_queued_ms": message.queued,
            "fcm": {
                "id": message.id,
                "from": message.from_,
                "to": message.to,
                "category": message.category,
                "persistent_id": persistent_id,
                "stream_id": message.stream_id,
                "from_trusted_server": message.from_trusted_server,
                "ttl": message.ttl,
                "immediate_ack": message.immediate_ack,
            },
            "app_data": [{"key": item.key, "value": item.value} for item in message.app_data],
            "raw_data_base64": (
                base64.b64encode(message.raw_data).decode("ascii")
                if message.raw_data is not None
                else None
            ),
            "payload": payload,
        }

        with self._lock:
            state = read_json(self.state_path)
            known_ids = list(state.get("received_persistent_ids", []))
            duplicate = bool(persistent_id and persistent_id in known_ids)
            if not duplicate:
                _append_private(self.events_path, record)
                if persistent_id:
                    known_ids.append(persistent_id)
                    state["received_persistent_ids"] = known_ids[-1000:]
                    atomic_json(self.state_path, state)
            if persistent_id:
                client.persistent_ids = list(
                    dict.fromkeys(client.persistent_ids + [persistent_id])
                )[-1000:]

        if not duplicate and event_type != "unclassified" and self.on_event is not None:
            self.on_event()

        if not duplicate:
            if event_type == "doorbell_press":
                print(f"{received_at} Blink doorbell press received", flush=True)
            elif event_type == "camera_motion":
                print(f"{received_at} Blink camera motion received", flush=True)
            else:
                print(f"{received_at} Blink push received (unclassified)", flush=True)

        try:
            did_ack = acknowledge_notification(self.data_dir, payload)
        except BlinkAccountError as error:
            _append_private(self.events_path, {
                "kind": "blink_ack_error",
                "received_at": utc_now(),
                "persistent_id": persistent_id,
                "stage": error.stage,
                "reason": error.reason,
            })
            print("Blink receipt acknowledgement failed; details saved privately", flush=True)
        else:
            if did_ack:
                _append_private(self.events_path, {
                    "kind": "blink_ack_sent",
                    "received_at": utc_now(),
                    "persistent_id": persistent_id,
                })
