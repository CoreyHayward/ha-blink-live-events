from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .capture import EVENTS_NAME


def _safe_value(value: Any) -> str | int | float | bool | None:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value[:120] if isinstance(value, str) else value
    return None


def summarize(data_dir: Path) -> None:
    path = data_dir / EVENTS_NAME
    if not path.exists():
        print("No push messages have been captured yet.")
        return

    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("kind") != "fcm_message":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            safe_record = {
                "received_at": _safe_value(record.get("received_at")),
                "classification": _safe_value(record.get("classification")),
                "event_type": _safe_value(payload.get("event_type")),
                "camera_name": _safe_value(payload.get("camera_name")),
                "created_at": _safe_value(payload.get("created_at")),
                "provider_sent_ms": _safe_value(record.get("provider_sent_ms")),
                "provider_queued_ms": _safe_value(record.get("provider_queued_ms")),
            }
            print(json.dumps(safe_record, separators=(",", ":"), sort_keys=True))
            count += 1
    if count == 0:
        print("No push messages have been captured yet.")
