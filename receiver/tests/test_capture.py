from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from receiver.blink_live_events.capture import MessageCapture, classify
from receiver.vendor.fcm_receiver.messages_manual import AppData, DataMessageStanza


class CaptureWakeTests(unittest.TestCase):
    def test_cv_motion_is_classified_as_camera_motion(self) -> None:
        self.assertEqual(
            classify({"category": "media", "event_type": "cv_motion"}),
            "camera_motion",
        )

    def test_doorbell_pir_motion_is_classified_as_camera_motion(self) -> None:
        self.assertEqual(
            classify({"category": "media", "event_type": "pir"}),
            "camera_motion",
        )

    def test_pan_tilt_camera_pir_is_classified_as_camera_motion(self) -> None:
        self.assertEqual(
            classify(
                {
                    "category": "media",
                    "event_type": "pir",
                    "camera_name": "Pan-Tilt Camera",
                }
            ),
            "camera_motion",
        )

    def test_doorbell_pir_motion_wakes_delivery_after_persist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            (data_dir / "fcm-state.json").write_text("{}", encoding="utf-8")
            wake_checks: list[bool] = []

            def wake() -> None:
                rows = [
                    json.loads(line)
                    for line in (data_dir / "messages.ndjson").read_text().splitlines()
                ]
                wake_checks.append(any(row.get("classification") == "camera_motion" for row in rows))

            capture = MessageCapture(data_dir, on_event=wake)
            message = DataMessageStanza(
                id="pir-message-id",
                category="media",
                app_data=[AppData("event_type", "pir"), AppData("camera_name", "Doorbell")],
            )
            capture.handle(message, SimpleNamespace(persistent_ids=[]))

            self.assertEqual(wake_checks, [True])

    def test_classified_event_wakes_delivery_after_persist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            (data_dir / "fcm-state.json").write_text("{}", encoding="utf-8")
            wake_checks: list[bool] = []

            def wake() -> None:
                rows = [
                    json.loads(line)
                    for line in (data_dir / "messages.ndjson").read_text().splitlines()
                ]
                wake_checks.append(any(row.get("classification") == "doorbell_press" for row in rows))

            capture = MessageCapture(data_dir, on_event=wake)
            message = DataMessageStanza(
                id="message-id",
                category="media",
                app_data=[AppData("event_type", "button_press")],
            )
            capture.handle(message, SimpleNamespace(persistent_ids=[]))

            self.assertEqual(wake_checks, [True])

    def test_unknown_event_type_is_classified_as_other(self) -> None:
        self.assertEqual(
            classify(
                {
                    "category": "unrecognized-category",
                    "event_type": "new_sensor_activity",
                    "camera_name": "Unlisted camera model",
                }
            ),
            "other",
        )
        self.assertEqual(classify({"event_type": "new_sensor_activity"}), "other")

    def test_unknown_event_type_wakes_delivery_after_persist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            (data_dir / "fcm-state.json").write_text("{}", encoding="utf-8")
            wake_checks: list[bool] = []

            def wake() -> None:
                rows = [
                    json.loads(line)
                    for line in (data_dir / "messages.ndjson").read_text().splitlines()
                ]
                wake_checks.append(any(row.get("classification") == "other" for row in rows))

            capture = MessageCapture(data_dir, on_event=wake)
            message = DataMessageStanza(
                id="new-event-message-id",
                category="unknown",
                app_data=[AppData("event_type", "new_sensor_activity")],
            )

            capture.handle(message, SimpleNamespace(persistent_ids=[]))

            self.assertEqual(wake_checks, [True])

    def test_event_without_event_type_does_not_wake_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            (data_dir / "fcm-state.json").write_text("{}", encoding="utf-8")
            wake_checks: list[bool] = []
            capture = MessageCapture(data_dir, on_event=lambda: wake_checks.append(True))
            message = DataMessageStanza(
                id="message-id",
                category="unknown",
                app_data=[AppData("camera_name", "Unknown camera")],
            )

            capture.handle(message, SimpleNamespace(persistent_ids=[]))

            self.assertEqual(wake_checks, [])


if __name__ == "__main__":
    unittest.main()
