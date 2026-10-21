from __future__ import annotations

import base64
import hashlib
import hmac
import getpass
import json
import platform
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .state import atomic_json, ensure_private_dir, read_json


OAUTH_TOKEN_URL = "https://api.oauth.blink.com/oauth/token"
REST_ROOT = "https://rest-prod.immedia-semi.com/api"
APP_VERSION = "60.0 (29834864)"
USER_AGENT = "Blink/60.0 (Standalone receiver)"
OAUTH_CLIENT_ID = "android"
OAUTH_REDIRECT_URI = "https://applinks.blink.com/signin/callback"
OAUTH_SCOPE = "client"
OAUTH_AUTH_APP_VERSION = "Version 60.0"
OAUTH_LOGIN_TTL_SECONDS = 15 * 60
AUTH_STATE_NAME = "blink-auth.json"


class BlinkAccountError(RuntimeError):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


def _request(method: str, url: str, *, headers: dict[str, str],
             form: dict[str, str] | None = None,
             body: dict[str, Any] | None = None) -> tuple[int, Any, bytes]:
    data = None
    request_headers = {"User-Agent": USER_AGENT, **headers}
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        # The status is enough to choose the OAuth retry path. Avoid reading or
        # logging provider bodies that may include account or session details.
        return error.code, error.headers, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        raise BlinkAccountError("network", "request_failed") from None


def _json_object(data: bytes, stage: str) -> dict[str, Any]:
    try:
        result = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BlinkAccountError(stage, "invalid_json_response") from None
    if not isinstance(result, dict):
        raise BlinkAccountError(stage, "invalid_json_response")
    return result


def _oauth_token(state: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    expires_at = float(state.get("expires_at", 0) or 0)
    if state.get("access_token") and expires_at > time.time() + 60:
        return state

    refresh_token = state.get("refresh_token")
    if not refresh_token:
        raise BlinkAccountError("oauth", "no_receiver_session")
    hardware_id = state.get("hardware_id")
    if not hardware_id:
        raise BlinkAccountError("oauth_refresh", "hardware_id_missing")

    oauth_client_id = state.get("oauth_client_id", "ios")
    if oauth_client_id == OAUTH_CLIENT_ID:
        refresh_form = {
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "client_id": OAUTH_CLIENT_ID,
            "scope": OAUTH_SCOPE,
        }
        refresh_headers = {"Accept": "application/json"}
    else:
        # Preserve the existing BlinkPy/iOS refresh contract for any older
        # state while Android hosted sessions use the APK-derived form.
        from blinkpy.helpers.constants import (
            OAUTH_SCOPE as IOS_OAUTH_SCOPE,
            OAUTH_TOKEN_USER_AGENT,
            OAUTH_V2_CLIENT_ID,
        )
        refresh_form = {
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "client_id": OAUTH_V2_CLIENT_ID,
            "scope": IOS_OAUTH_SCOPE,
            "hardware_id": hardware_id,
        }
        refresh_headers = {
            "User-Agent": OAUTH_TOKEN_USER_AGENT,
            "Accept": "*/*",
        }
    status, _, response = _request(
        "POST",
        OAUTH_TOKEN_URL,
        headers=refresh_headers,
        form=refresh_form,
    )
    if status != 200:
        raise BlinkAccountError("oauth_refresh", f"http_{status}")
    token_data = _json_object(response, "oauth_refresh")
    state.update(_token_fields(token_data))
    atomic_json(data_dir / AUTH_STATE_NAME, state)
    return state


def _token_fields(token_data: dict[str, Any]) -> dict[str, Any]:
    access = token_data.get("access_token")
    refresh = token_data.get("refresh_token")
    expires = token_data.get("expires_in")
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
        raise BlinkAccountError("oauth", "token_response_incomplete")
    try:
        expires_seconds = int(expires)
    except (TypeError, ValueError):
        expires_seconds = 3600
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": int(time.time()) + max(60, expires_seconds),
    }


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _authorization_url(hardware_id: str, state: str, code_challenge: str) -> str:
    # The current APK passes BuildConfig.VERSION_NAME to its Unified Sign-In
    # profile; the Version prefix and remaining hosted parameters follow the
    # published 57.1 trace. A fresh standalone token exchange remains unproven.
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "hardware_id": hardware_id,
        "app_brand": "blink",
        "app_version": OAUTH_AUTH_APP_VERSION,
        "device_brand": "Raspberry Pi",
        "device_model": "Homebridge",
        "device_os_version": "Android 14",
        "dark_mode": "false",
    }
    return "https://api.oauth.blink.com/oauth/v2/authorize?" + urllib.parse.urlencode(params)


def _callback_code(callback_url: str, expected_state: str) -> str:
    if not callback_url or len(callback_url.encode("utf-8")) > 2048:
        raise BlinkAccountError("oauth_callback", "invalid_callback")
    if any(ord(char) <= 0x20 or ord(char) == 0x7F or char == "#" for char in callback_url):
        raise BlinkAccountError("oauth_callback", "invalid_callback")
    try:
        parsed = urllib.parse.urlsplit(callback_url)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except (ValueError, UnicodeError):
        raise BlinkAccountError("oauth_callback", "invalid_callback") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "applinks.blink.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/signin/callback"
        or parsed.fragment
    ):
        raise BlinkAccountError("oauth_callback", "invalid_callback")

    states = query.get("state", [])
    codes = query.get("code", [])
    errors = query.get("error", [])
    descriptions = query.get("error_description", [])
    if (
        len(states) != 1
        or len(codes) > 1
        or len(errors) > 1
        or len(descriptions) > 1
        or bool(codes) == bool(errors)
        or (descriptions and not errors)
    ):
        raise BlinkAccountError("oauth_callback", "invalid_callback")
    if not hmac.compare_digest(states[0], expected_state):
        raise BlinkAccountError("oauth_callback", "state_mismatch")
    if errors:
        raise BlinkAccountError("oauth_callback", "sign_in_not_completed")
    if not codes[0]:
        raise BlinkAccountError("oauth_callback", "invalid_callback")
    return codes[0]


def _hosted_android_login(data_dir: Path) -> dict[str, Any]:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise BlinkAccountError("oauth_login", "interactive_tty_required")
    started_at = time.time()
    hardware_id = str(uuid.uuid4()).upper()
    oauth_state = _base64url(secrets.token_bytes(32))
    verifier = _base64url(secrets.token_bytes(64))
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    authorization_url = _authorization_url(hardware_id, oauth_state, challenge)
    print(
        "\nOpen this Blink-hosted sign-in URL in a trusted browser. Complete the "
        "Blink sign-in and verification there; the receiver never sees your password or MFA code.\n",
        flush=True,
    )
    print(authorization_url, flush=True)
    callback = getpass.getpass(
        "\nAfter Blink redirects to applinks.blink.com/signin/callback, paste the full address-bar URL here (hidden): "
    ).strip()
    if time.time() > started_at + OAUTH_LOGIN_TTL_SECONDS:
        raise BlinkAccountError("oauth_callback", "sign_in_expired")
    authorization_code = _callback_code(callback, oauth_state)
    status, _, response = _request(
        "POST",
        OAUTH_TOKEN_URL,
        headers={"Accept": "application/json"},
        form={
            "grant_type": "authorization_code",
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code": authorization_code,
            "code_verifier": verifier,
            "client_id": OAUTH_CLIENT_ID,
        },
    )
    if status != 200:
        raise BlinkAccountError("oauth_token_exchange", f"http_{status}")
    token_data = _json_object(response, "oauth_token_exchange")
    state = {
        "format": 2,
        "hardware_id": hardware_id,
        "oauth_client_id": OAUTH_CLIENT_ID,
        **_token_fields(token_data),
    }
    atomic_json(data_dir / AUTH_STATE_NAME, state)
    return state


def _discover_account(state: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    state = _oauth_token(state, data_dir)
    access = state["access_token"]
    headers = {"Authorization": f"Bearer {access}"}
    tier = state.get("tier")
    account_id = state.get("account_id")
    if not tier or account_id is None:
        status, _, response = _request(
            "GET", f"{REST_ROOT}/v1/users/tier_info", headers=headers
        )
        if status != 200:
            raise BlinkAccountError("tier_info", f"http_{status}")
        tier_info = _json_object(response, "tier_info")
        tier = tier_info.get("tier")
        account_id = tier_info.get("account_id")
    if not isinstance(tier, str) or not tier or account_id is None:
        raise BlinkAccountError("tier_info", "account_details_missing")

    rest_root = f"https://rest-{tier}.immedia-semi.com/api"
    status, response_headers, _ = _request(
        "GET",
        f"{rest_root}/v3/accounts/{urllib.parse.quote(str(account_id), safe='')}/homescreen",
        headers=headers,
    )
    if status != 200:
        raise BlinkAccountError("client_discovery", f"http_{status}")
    client_id = response_headers.get("Client-Id")
    if not client_id:
        raise BlinkAccountError("client_discovery", "client_id_header_missing")

    state.update({"tier": tier, "account_id": str(account_id), "client_id": client_id})
    return state


def associate_fcm_token(data_dir: Path, client_name: str = "Blink Live Events") -> Path:
    """Create/refresh a separate Blink session and associate this FCM token."""
    ensure_private_dir(data_dir)
    fcm_state = read_json(data_dir / "fcm-state.json")
    if fcm_state.get("status") != "ready" or not fcm_state.get("fcm_token"):
        raise BlinkAccountError("fcm", "fcm_registration_not_ready")

    auth_path = data_dir / AUTH_STATE_NAME
    if auth_path.exists():
        auth_state = read_json(auth_path)
        try:
            auth_state = _oauth_token(auth_state, data_dir)
        except BlinkAccountError:
            auth_state = _hosted_android_login(data_dir)
    else:
        auth_state = _hosted_android_login(data_dir)

    auth_state = _discover_account(auth_state, data_dir)

    rest_host = f"https://rest-{auth_state['tier']}.immedia-semi.com"
    body = {
        "app_version": APP_VERSION,
        "os_version": platform.release() or "standalone",
        "client_name": client_name,
        "notification_key": fcm_state["fcm_token"],
    }
    status, _, _ = _request(
        "POST",
        f"{rest_host}/clients/{urllib.parse.quote(str(auth_state['client_id']), safe='')}/update",
        headers={
            "Authorization": f"Bearer {auth_state['access_token']}",
            "Client-Id": str(auth_state["client_id"]),
        },
        body=body,
    )
    if status < 200 or status >= 300:
        raise BlinkAccountError("client_update", f"http_{status}")
    atomic_json(auth_path, auth_state)
    return auth_path


def acknowledge_notification(data_dir: Path, payload: dict[str, Any]) -> bool:
    """Send Blink's app-level receipt for a push that asks for one."""
    return_receipt = str(payload.get("return_receipt", "")).lower()
    if return_receipt not in ("1", "true", "yes"):
        return False
    state = read_json(data_dir / AUTH_STATE_NAME)
    state = _oauth_token(state, data_dir)
    transaction_id = payload.get("unique_id")
    tier = payload.get("tier")
    if not transaction_id or not tier:
        return False
    transaction_id = str(transaction_id)
    tier = str(tier)

    local_account = str(state.get("account_id", ""))
    same_tier = tier == state.get("tier")
    same_account = str(payload.get("account_id", "")) == local_account
    body = {
        "transaction_id": transaction_id,
        "status": "RECEIVED" if same_tier and same_account else "UNWANTED",
    }
    rest_root = f"https://rest-{state['tier']}.immedia-semi.com/api"
    status, _, _ = _request(
        "POST",
        f"{rest_root}/v2/notification",
        headers={
            "Authorization": f"Bearer {state['access_token']}",
            "Client-Id": str(state["client_id"]),
        },
        body=body,
    )
    if status < 200 or status >= 300:
        raise BlinkAccountError("notification_ack", f"http_{status}")
    atomic_json(data_dir / AUTH_STATE_NAME, state)
    return True
