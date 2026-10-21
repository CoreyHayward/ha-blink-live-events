from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from receiver.blink_live_events.ha_delivery import (
    HomeAssistantWebhook,
    build_ha_event,
    deliver_pending_once,
    initialize_delivery_checkpoint,
)


def _motion_record() -> dict[str, object]:
    return {
        "kind": "fcm_message",
        "received_at": "2026-01-01T12:00:00.250Z",
        "classification": "camera_motion",
        "provider_sent_ms": 1767268800200,
        "fcm": {"id": "private-fcm-id", "persistent_id": "private-persistent-id"},
        "payload": {
            "category": "motion",
            "event_type": "cam2sm_motion",
            "camera_name": "Test camera",
            "unique_id": "private-blink-transaction-id",
            "return_receipt": "true",
        },
    }


def _other_record() -> dict[str, object]:
    return {
        "kind": "fcm_message",
        "received_at": "2026-01-01T12:01:00.250Z",
        "classification": "other",
        "provider_sent_ms": 1767268860200,
        "fcm": {"id": "private-other-fcm-id", "persistent_id": "private-other-persistent-id"},
        "payload": {
            "category": "new_category",
            "event_type": "new_sensor_activity",
            "camera_name": "Unlisted camera model",
        },
    }


class FakeWebhook:
    def __init__(self, fail: bool = False) -> None:
        self.events: list[dict[str, object]] = []
        self.fail = fail

    def send(self, event: dict[str, object]) -> None:
        if self.fail:
            self.fail = False
            raise OSError("temporary failure")
        self.events.append(event)


def _append_event(data_dir: Path) -> None:
    with (data_dir / "messages.ndjson").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(_motion_record()) + "\n")


class HomeAssistantDeliveryTests(unittest.TestCase):
    def test_event_is_sanitized_and_contains_provider_time(self) -> None:
        event = build_ha_event(_motion_record())
        serialized = json.dumps(event)
        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["classification"], "camera_motion")
        self.assertEqual(event["provider_timestamp"], "2026-01-01T12:00:00.200Z")
        self.assertEqual(event["received_at"], "2026-01-01T12:00:00.250Z")
        self.assertNotIn("private-fcm-id", serialized)
        self.assertNotIn("private-persistent-id", serialized)
        self.assertNotIn("private-blink-transaction-id", serialized)

    def test_unrecognized_event_is_delivered_with_safe_metadata(self) -> None:
        event = build_ha_event(_other_record())
        serialized = json.dumps(event)
        self.assertEqual(event["classification"], "other")
        self.assertEqual(event["event_type"], "new_sensor_activity")
        self.assertEqual(event["camera_name"], "Unlisted camera model")
        self.assertNotIn("private-other-fcm-id", serialized)
        self.assertNotIn("private-other-persistent-id", serialized)

        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            initialize_delivery_checkpoint(data_dir)
            with (data_dir / "messages.ndjson").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(_other_record()) + "\n")
            webhook = FakeWebhook()

            self.assertEqual(deliver_pending_once(data_dir, webhook), (1, 0))
            self.assertEqual(webhook.events, [event])

    def test_successful_events_are_not_delivered_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            initialize_delivery_checkpoint(data_dir)
            _append_event(data_dir)
            webhook = FakeWebhook()

            self.assertEqual(deliver_pending_once(data_dir, webhook), (1, 0))
            self.assertEqual(deliver_pending_once(data_dir, webhook), (0, 0))
            self.assertEqual(len(webhook.events), 1)

    def test_failed_delivery_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            initialize_delivery_checkpoint(data_dir)
            _append_event(data_dir)
            webhook = FakeWebhook(fail=True)

            self.assertEqual(deliver_pending_once(data_dir, webhook), (0, 1))
            self.assertEqual(deliver_pending_once(data_dir, webhook), (1, 0))
            self.assertEqual(len(webhook.events), 1)

    def test_initialization_skips_historical_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            _append_event(data_dir)
            webhook = FakeWebhook()

            self.assertTrue(initialize_delivery_checkpoint(data_dir))
            self.assertEqual(deliver_pending_once(data_dir, webhook), (0, 0))
            self.assertEqual(webhook.events, [])

    def test_webhook_url_must_be_an_api_webhook(self) -> None:
        with self.assertRaises(ValueError):
            HomeAssistantWebhook("http://ha.local:8123/api/events/blink")


if __name__ == "__main__":
    unittest.main()
