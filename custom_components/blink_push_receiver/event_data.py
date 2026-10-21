"""Validation and privacy filtering for events sent by the receiver."""

from __future__ import annotations

from typing import Any

from .const import (
    CLASSIFICATION_DOORBELL,
    CLASSIFICATION_MOTION,
    CLASSIFICATIONS,
    DOMAIN,
)


def _optional_string(value: Any, *, max_length: int = 160) -> str | None:
    """Return a bounded string, ignoring unexpected values."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:max_length] or None


def normalize_event(body: dict[str, Any]) -> dict[str, Any] | None:
    """Return the documented allowlisted event data, or ``None`` if invalid."""
    schema_version = body.get("schema_version", 1)
    if type(schema_version) is not int or schema_version != 1:
        return None

    classification = body.get("classification")
    if not isinstance(classification, str) or classification not in CLASSIFICATIONS:
        return None

    event_id = _optional_string(body.get("event_id"), max_length=128)
    if event_id is None:
        return None

    normalized: dict[str, Any] = {
        "schema_version": schema_version,
        "source": DOMAIN,
        "event_id": event_id,
        "classification": classification,
    }
    for key, max_length in (
        ("category", 80),
        ("event_type", 80),
        ("camera_name", 120),
        ("provider_timestamp", 48),
        ("created_at", 48),
        ("received_at", 48),
    ):
        if (
            value := _optional_string(body.get(key), max_length=max_length)
        ) is not None:
            normalized[key] = value

    if classification == CLASSIFICATION_DOORBELL:
        normalized["ha_event_type"] = "ring"
    elif classification == CLASSIFICATION_MOTION:
        normalized["ha_event_type"] = "motion"

    return normalized
