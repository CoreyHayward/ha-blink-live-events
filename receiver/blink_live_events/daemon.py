from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Any

from ..vendor.fcm_receiver.fcm_client import FCMClient
from .capture import MessageCapture
from .ha_delivery import (
    initialize_delivery_checkpoint,
    run_delivery_worker,
    webhook_url_from_environment,
)
from .state import read_json


def listen(data_dir: Path, heartbeat_seconds: int = 600) -> None:
    fcm_state_path = data_dir / "fcm-state.json"
    auth_state_path = data_dir / "blink-auth.json"
    fcm_state = read_json(fcm_state_path)
    if fcm_state.get("status") != "ready":
        raise RuntimeError("FCM registration is not ready; run register-fcm first")
    auth_state = read_json(auth_state_path)
    if not all(auth_state.get(key) for key in ("tier", "account_id", "client_id")):
        raise RuntimeError("Blink account association is incomplete; run register-blink first")

    webhook_url = webhook_url_from_environment()
    delivery_wake = threading.Event()
    capture = MessageCapture(data_dir, on_event=delivery_wake.set if webhook_url else None)
    client = FCMClient()
    client.android_id = int(fcm_state["android_id"])
    client.security_token = int(fcm_state["security_token"])
    client.persistent_ids = list(fcm_state.get("received_persistent_ids", []))[-1000:]
    client.project_id = str(fcm_state.get("project_id", ""))
    client.heartbeat_interval_sec = heartbeat_seconds

    login_failed = threading.Event()
    stop_requested = threading.Event()

    def request_stop(_signum: int, _frame: Any) -> None:
        stop_requested.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    delivery_thread = None
    if webhook_url:
        if initialize_delivery_checkpoint(data_dir):
            print("Existing Blink events will not be replayed to Home Assistant", flush=True)
        delivery_thread = threading.Thread(
            target=run_delivery_worker,
            args=(data_dir, webhook_url, stop_requested, delivery_wake),
            name="home-assistant-webhook-delivery",
            daemon=True,
        )
        delivery_thread.start()
    else:
        print("Home Assistant webhook forwarding is not configured", flush=True)

    def on_raw_message(message: Any, _identifier: str) -> None:
        capture.handle(message, client)

    def on_status(status: str, _identifier: str) -> None:
        if status == "connected":
            print("FCM transport connected; waiting for Blink pushes", flush=True)
        elif status == "login_failed":
            login_failed.set()
            print("FCM transport login rejected", flush=True)
        elif status == "reconnecting":
            print("FCM transport reconnecting", flush=True)
        elif status == "disconnected":
            print("FCM transport disconnected", flush=True)

    client.on_raw_message = on_raw_message
    client.on_connection_status = on_status
    client.start_listening()
    try:
        while True:
            if login_failed.is_set():
                raise RuntimeError("FCM transport login rejected; check the independent registration state")
            if stop_requested.wait(1):
                break
        print("Stopping Blink Live Events receiver", flush=True)
    finally:
        stop_requested.set()
        delivery_wake.set()
        client.close()
        if delivery_thread is not None:
            delivery_thread.join(timeout=3)
