from __future__ import annotations

import base64
import json
import secrets
import urllib.parse
import urllib.request
from typing import Optional, Tuple


from .marshal_manual import marshal_android_checkin_request
from .messages_manual import (
    AndroidCheckinRequest,
    AndroidCheckinProto,
    ChromeBuildProto,
)
from .unmarshal_manual import unmarshal_android_checkin_response


CHECKIN_URL = "https://android.clients.google.com/checkin"
REGISTER_URL = "https://android.clients.google.com/c2dm/register3"
FIREBASE_INSTALLATION = "https://firebaseinstallations.googleapis.com/v1/"
FIREBASE_REGISTRATION = "https://fcmregistrations.googleapis.com/v1/"
FCM_ENDPOINT_URL = "https://fcm.googleapis.com/fcm/send"

# From Go consts.go
FCM_SERVER_KEY = bytes([
    4, 51, 148, 247, 223, 161, 235, 177, 220, 3, 162, 94, 21, 113, 219, 72,
    211, 46, 237, 237, 178, 52, 219, 183, 71, 58, 12, 143, 196, 204, 225, 111,
    60, 140, 132, 223, 171, 182, 102, 62, 242, 12, 212, 139, 254, 227, 249,
    118, 47, 20, 28, 99, 8, 106, 111, 45, 177, 26, 149, 176, 206, 55, 192, 156,
    110,
])


def _generate_topic_kid() -> str:
    rand = secrets.randbits(32)
    return f"|ID|{rand}|"


def send_gcm_checkin_request(req: AndroidCheckinRequest) -> Tuple[int, int]:
    data = marshal_android_checkin_request(req)
    http_req = urllib.request.Request(
        CHECKIN_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-protobuf",
            "User-Agent": "",
        },
    )
    with urllib.request.urlopen(http_req) as resp:
        body = resp.read()
        if resp.status // 100 != 2:
            raise RuntimeError(f"checkin HTTP {resp.status}: {body!r}")
    parsed = unmarshal_android_checkin_response(body)
    if parsed.android_id is None or parsed.security_token is None:
        raise RuntimeError("checkin response missing android_id/security_token")
    return int(parsed.android_id), int(parsed.security_token)


def send_gcm_register_request(
    android_id: int,
    security_token: int,
    app_id: str,
    android_app: Optional[dict] = None,
    installation_auth_token: Optional[str] = None,
) -> str:
    values = []
    if not android_app or not installation_auth_token:
        values.extend(
            [
                ("X-subtype", app_id),
                ("app", "org.chromium.linux"),
                ("device", str(android_id)),
                ("sender", base64.urlsafe_b64encode(FCM_SERVER_KEY).rstrip(b"=").decode()),
            ]
        )
    else:
        values.extend(
            [
                ("X-subtype", android_app["gcm_sender_id"]),
                ("device", str(android_id)),
                ("app", android_app["android_package"]),
                ("cert", android_app["android_package_cert"]),
                ("app_ver", "1"),
                ("X-app_ver", "1"),
                ("X-osv", "29"),
                ("X-cliv", "fiid-21.1.1"),
                ("X-gmsv", "220217001"),
                ("X-scope", "*"),
                ("X-Goog-Firebase-Installations-Auth", installation_auth_token),
                ("X-gms_app_id", app_id),
                ("X-Firebase-Client", "android-min-sdk/23 fire-core/20.0.0 fire-installations/17.0.0 fire-fcm/22.0.0"),
                ("X-Firebase-Client-Log-Type", "1"),
                ("X-app_ver_name", "1"),
                ("target_ver", "31"),
                ("sender", android_app["gcm_sender_id"]),
            ]
        )

    body = urllib.parse.urlencode(values).encode()
    http_req = urllib.request.Request(
        REGISTER_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"AidLogin {android_id}:{security_token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "",
        },
    )
    with urllib.request.urlopen(http_req) as resp:
        result = resp.read()
    # Response is key=value lines; parse as query-string
    parsed = urllib.parse.parse_qs(result.decode())
    if "Error" in parsed and parsed["Error"]:
        raise RuntimeError(parsed["Error"][0])
    token = parsed.get("token", [None])[0]
    if not token:
        raise RuntimeError("missing token in GCM register response")
    return token


def send_fcm_install_request(api_key: str, project_id: str, app_id: str, android: bool = False) -> str:
    # Generate a valid FID (17 bytes) with high nibble 0b0111, then base64-std
    import os

    fid_bytes = bytearray(os.urandom(17))
    fid_bytes[0] = 0b01110000 + (fid_bytes[0] % 0b00010000)
    fid = base64.b64encode(bytes(fid_bytes)).decode().strip()
    body = {
        "fid": fid,
        "appId": app_id,
        "authVersion": "FIS_v2",
        "sdkVersion": "a:17.0.0" if android else "w:0.6.4",
    }
    data = json.dumps(body).encode()
    http_req = urllib.request.Request(
        f"{FIREBASE_INSTALLATION}projects/{project_id}/installations",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            **(
                {
                    "x-firebase-client": base64.b64encode(json.dumps({"heartbeats": [], "version": 2}).encode()).decode()
                }
                if not android
                else {
                    "X-Android-Package": "",
                    "X-Android-Cert": "",
                    "x-firebase-client": "android-min-sdk/23 fire-core/20.0.0 fire-installations/17.0.0 fire-fcm/22.0.0",
                    "x-firebase-client-log-type": "3",
                    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11)",
                }
            ),
        },
    )
    with urllib.request.urlopen(http_req) as resp:
        result = json.loads(resp.read().decode())
    token = result.get("authToken", {}).get("token")
    if not token:
        raise RuntimeError("failed to obtain installation auth token")
    return token


def send_fcm_register_request(
    api_key: str,
    project_id: str,
    gcm_token: str,
    p256dh_public_key_b64url: str,
    auth_secret_b64url: str,
    installation_auth_token: Optional[str] = None,
) -> str:
    body = {
        "web": {
            "applicationPubKey": "",  # optional VAPID application key; keep empty like Go default
            "auth": auth_secret_b64url,
            "endpoint": f"{FCM_ENDPOINT_URL}/{gcm_token}",
            "p256dh": p256dh_public_key_b64url,
        }
    }
    data = json.dumps(body).encode()
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    if installation_auth_token:
        headers["x-goog-firebase-installations-auth"] = installation_auth_token
    http_req = urllib.request.Request(
        f"{FIREBASE_REGISTRATION}projects/{project_id}/registrations",
        data=data,
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(http_req) as resp:
        result = json.loads(resp.read().decode())
    token = result.get("token")
    if not token:
        raise RuntimeError("failed to obtain FCM token")
    return token


def send_topic_subscription_request(
    android_id: int,
    security_token: int,
    fcm_token: str,
    topic_path: str,
    *,
    app: str = "org.chromium.linux",
    app_ver: str = "1",
    app_ver_name: str = "1",
    gms_app_id: Optional[str] = None,
    delete: bool = False,
    kid: Optional[str] = None,
) -> dict:
    if not android_id or not security_token:
        raise ValueError("android_id and security_token are required")
    if not fcm_token:
        raise ValueError("fcm_token is required for topic operations")
    kid_value = kid or _generate_topic_kid()
    values = [
        ("X-subtype", fcm_token),
        ("sender", fcm_token),
        ("device", str(android_id)),
    ]
    if app:
        values.append(("app", app))
    if app_ver:
        values.append(("app_ver", app_ver))
        values.append(("X-app_ver", app_ver))
    if app_ver_name:
        values.append(("X-app_ver_name", app_ver_name))
    if gms_app_id:
        values.append(("X-gms_app_id", gms_app_id))
    values.extend(
        [
            ("X-gcm.topic", topic_path),
            ("X-scope", topic_path),
            ("X-subscription", fcm_token),
            ("X-kid", kid_value),
        ]
    )
    if delete:
        values.append(("delete", "1"))
        values.append(("X-delete", "1"))

    body = urllib.parse.urlencode(values).encode()
    http_req = urllib.request.Request(
        REGISTER_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"AidLogin {android_id}:{security_token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "",
        },
    )
    with urllib.request.urlopen(http_req) as resp:
        response_body = resp.read().decode()
    parsed = urllib.parse.parse_qs(response_body, keep_blank_values=True)
    if "Error" in parsed and parsed["Error"]:
        raise RuntimeError(parsed["Error"][0])
    token = parsed.get("token", [""])[0]
    return {
        "topic": topic_path,
        "token": token,
        "kid": kid_value,
        "raw": response_body,
        "deleted": delete,
        "action": "unsubscribe" if delete else "subscribe",
    }
