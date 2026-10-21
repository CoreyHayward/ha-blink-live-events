from __future__ import annotations

import base64
import json
import os
import secrets
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..vendor.fcm_receiver.http_client import (
    send_gcm_checkin_request,
    send_gcm_register_request,
)
from ..vendor.fcm_receiver.messages_manual import (
    AndroidCheckinProto,
    AndroidCheckinRequest,
    DeviceType,
)

from .state import atomic_json, ensure_private_dir, read_json


ANDROID_PACKAGE = "com.immediasemi.android.blink"
ANDROID_CERT_SHA1 = "65902c52c99a37502bdd4f342db2180c4c73b578"
APP_VERSION_NAME = "60.0"
APP_VERSION_CODE = 29834864
FIS_URL = "https://firebaseinstallations.googleapis.com/v1"
STATE_NAME = "fcm-state.json"


class RegistrationError(RuntimeError):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.loads(response.read())
    if not isinstance(result, dict):
        raise RegistrationError("firebase_installation", "incomplete_response")
    return result


def _load_config(path: Path) -> dict[str, str]:
    value = read_json(path)
    required = ("google_api_key", "google_app_id", "project_id", "gcm_defaultSenderId")
    if any(not isinstance(value.get(key), str) or not value[key] for key in required):
        raise RegistrationError("firebase_config", "missing_required_field")
    return {key: value[key] for key in required}


def _new_fid() -> str:
    raw = bytearray(secrets.token_bytes(17))
    raw[0] = 0x70 | (raw[0] & 0x0F)
    return base64.b64encode(raw).decode("ascii").rstrip("=")


def _create_firebase_installation(config: dict[str, str], fid: str) -> dict[str, Any]:
    headers = {
        "x-goog-api-key": config["google_api_key"],
        "X-Android-Package": ANDROID_PACKAGE,
        "X-Android-Cert": ANDROID_CERT_SHA1,
        "x-firebase-client": (
            "android-min-sdk/23 fire-core/20.0.0 "
            "fire-installations/17.0.0 fire-fcm/22.0.0"
        ),
        "x-firebase-client-log-type": "3",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 14)",
    }
    body = {
        "fid": fid,
        "appId": config["google_app_id"],
        "authVersion": "FIS_v2",
        "sdkVersion": "a:17.0.0",
    }
    return _post_json(
        f"{FIS_URL}/projects/{config['project_id']}/installations", body, headers
    )


def _private_state(config: dict[str, str], fis: dict[str, Any], fid: str,
                   android_id: int, security_token: int) -> dict[str, Any]:
    auth = fis.get("authToken")
    if not isinstance(auth, dict) or not auth.get("token") or not fis.get("refreshToken"):
        raise RegistrationError("firebase_installation", "incomplete_response")
    return {
        "format": 1,
        "status": "gcm_registration_pending",
        "project_id": config["project_id"],
        "app_id": config["google_app_id"],
        "api_key": config["google_api_key"],
        "sender_id": config["gcm_defaultSenderId"],
        "package": ANDROID_PACKAGE,
        "cert_sha1": ANDROID_CERT_SHA1,
        "app_version_name": APP_VERSION_NAME,
        "app_version_code": APP_VERSION_CODE,
        "fid": fid,
        "fis_refresh_token": fis["refreshToken"],
        "fis_auth_token": auth["token"],
        "fis_auth_expires_in": auth.get("expiresIn"),
        "android_id": int(android_id),
        "security_token": int(security_token),
        "received_persistent_ids": [],
    }


def register_fcm(firebase_config: Path, data_dir: Path) -> Path:
    """Register an independent Android-app FCM identity and store it privately."""
    ensure_private_dir(data_dir)
    socket.setdefaulttimeout(25)
    state_path = data_dir / STATE_NAME
    if state_path.exists():
        state = read_json(state_path)
        if state.get("status") == "ready":
            return state_path
        if (
            not state.get("status")
            and state.get("fcm_token")
            and state.get("android_id")
            and state.get("security_token")
        ):
            # Migrate the private state created by the earlier investigation
            # script, which stored a working token without a status field.
            state["status"] = "ready"
            state.setdefault("received_persistent_ids", [])
            atomic_json(state_path, state)
            return state_path
        if state.get("status") != "gcm_registration_pending":
            raise RegistrationError("state", "existing_state_is_not_resumable")
    else:
        config = _load_config(firebase_config)
        fid = _new_fid()
        try:
            fis = _create_firebase_installation(config, fid)
        except urllib.error.HTTPError as error:
            raise RegistrationError("firebase_installation", f"http_{error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RegistrationError("firebase_installation", "network_error") from None

        checkin = AndroidCheckinRequest(
            locale="en_US",
            time_zone="GMT",
            checkin=AndroidCheckinProto(type=DeviceType.DEVICE_ANDROID_OS),
            version=3,
        )
        try:
            android_id, security_token = send_gcm_checkin_request(checkin)
        except urllib.error.HTTPError as error:
            raise RegistrationError("android_checkin", f"http_{error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RegistrationError("android_checkin", "network_error") from None
        except Exception:
            raise RegistrationError("android_checkin", "protocol_error") from None

        state = _private_state(config, fis, fid, android_id, security_token)
        atomic_json(state_path, state)

    app = {
        "gcm_sender_id": state["sender_id"],
        "android_package": ANDROID_PACKAGE,
        "android_package_cert": ANDROID_CERT_SHA1,
    }
    last_reason = "phone_registration_error"
    for attempt in range(10):
        try:
            token = send_gcm_register_request(
                android_id=int(state["android_id"]),
                security_token=int(state["security_token"]),
                app_id=state["app_id"],
                android_app=app,
                installation_auth_token=state["fis_auth_token"],
            )
            state["fcm_token"] = token
            state["status"] = "ready"
            atomic_json(state_path, state)
            return state_path
        except urllib.error.HTTPError as error:
            last_reason = f"http_{error.code}"
            break
        except urllib.error.URLError:
            last_reason = "network_error"
            break
        except RuntimeError as error:
            # The public receiver candidate reports this transient response for
            # some valid registrations; retrying the same independent identity
            # once per second succeeded during this investigation.
            if str(error) == "PHONE_REGISTRATION_ERROR" and attempt < 9:
                time.sleep(1)
                continue
            last_reason = str(error) if str(error).isupper() else "registration_error"
            break
        except Exception:
            last_reason = "protocol_error"
            break
    raise RegistrationError("android_fcm_registration", last_reason)
