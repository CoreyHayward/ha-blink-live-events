from __future__ import annotations

import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import receiver.blink_live_events.blink_account as blink_account
from receiver.blink_live_events.blink_account import (
    BlinkAccountError,
    OAUTH_REDIRECT_URI,
    _authorization_url,
    _callback_code,
    _hosted_android_login,
    _oauth_token,
    associate_fcm_token,
)
from receiver.blink_live_events.state import read_json


class HostedOAuthTests(unittest.TestCase):
    def test_authorization_url_uses_android_pkce_profile(self) -> None:
        url = _authorization_url("hardware-id", "state-value", "challenge-value")
        parsed = urlsplit(url)
        fields = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "api.oauth.blink.com")
        self.assertEqual(parsed.path, "/oauth/v2/authorize")
        self.assertEqual(fields["client_id"], ["android"])
        self.assertEqual(fields["app_version"], ["Version 60.0"])
        self.assertEqual(fields["redirect_uri"], [OAUTH_REDIRECT_URI])
        self.assertEqual(fields["response_type"], ["code"])
        self.assertEqual(fields["scope"], ["client"])
        self.assertEqual(fields["code_challenge_method"], ["S256"])
        self.assertEqual(fields["state"], ["state-value"])
        self.assertEqual(fields["code_challenge"], ["challenge-value"])

    def test_callback_accepts_only_matching_blink_app_link(self) -> None:
        callback = OAUTH_REDIRECT_URI + "?" + urlencode(
            {"code": "one-time+code", "state": "expected-state"}
        )

        self.assertEqual(_callback_code(callback, "expected-state"), "one-time+code")

    def test_callback_rejects_untrusted_or_ambiguous_values(self) -> None:
        invalid_callbacks = (
            "http://applinks.blink.com/signin/callback?code=x&state=s",
            "https://example.com/signin/callback?code=x&state=s",
            OAUTH_REDIRECT_URI + "?code=x&code=y&state=s",
            OAUTH_REDIRECT_URI + "?code=x&state=s&state=t",
            OAUTH_REDIRECT_URI + "?error=access_denied&state=s",
        )
        for callback in invalid_callbacks:
            with self.subTest(callback=callback):
                with self.assertRaises(BlinkAccountError):
                    _callback_code(callback, "s")

    def test_callback_rejects_state_mismatch(self) -> None:
        callback = OAUTH_REDIRECT_URI + "?" + urlencode(
            {"code": "one-time+code", "state": "wrong-state"}
        )
        with self.assertRaisesRegex(BlinkAccountError, "state_mismatch"):
            _callback_code(callback, "expected-state")

    def test_hosted_login_exchanges_hidden_callback_and_saves_android_profile(self) -> None:
        captured: dict[str, str] = {}
        tty = Mock()
        tty.isatty.return_value = True

        def authorization_url(hardware_id: str, state: str, challenge: str) -> str:
            captured["hardware_id"] = hardware_id
            captured["state"] = state
            captured["challenge"] = challenge
            return _authorization_url(hardware_id, state, challenge)

        def paste_callback(_prompt: str) -> str:
            return OAUTH_REDIRECT_URI + "?" + urlencode(
                {"code": "private-one-time-code", "state": captured["state"]}
            )

        token_response = json.dumps(
            {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}
        ).encode()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            blink_account.sys, "stdin", tty
        ), patch.object(blink_account.sys, "stderr", tty), patch.object(
            blink_account, "_authorization_url", side_effect=authorization_url
        ), patch.object(
            blink_account.getpass, "getpass", side_effect=paste_callback
        ), patch.object(
            blink_account, "_request", return_value=(200, {}, token_response)
        ) as request:
            stdout = StringIO()
            with redirect_stdout(stdout):
                state = _hosted_android_login(Path(directory))

        self.assertEqual(state["oauth_client_id"], "android")
        self.assertEqual(state["hardware_id"], captured["hardware_id"])
        self.assertEqual(request.call_args.kwargs["form"]["client_id"], "android")
        self.assertEqual(request.call_args.kwargs["form"]["code"], "private-one-time-code")
        self.assertEqual(
            stdout.getvalue().count("private-one-time-code"),
            0,
            "the one-time authorization code must not be printed",
        )

    def test_android_refresh_uses_android_form_and_persists_tokens(self) -> None:
        token_response = json.dumps(
            {"access_token": "access", "refresh_token": "refresh-2", "expires_in": 3600}
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            state = {
                "oauth_client_id": "android",
                "hardware_id": "hardware-id",
                "refresh_token": "refresh-1",
                "expires_at": 0,
            }
            with patch(
                "receiver.blink_live_events.blink_account._request",
                return_value=(200, {}, token_response),
            ) as request:
                refreshed = _oauth_token(state, data_dir)

            call = request.call_args.kwargs
            self.assertEqual(call["form"], {
                "refresh_token": "refresh-1",
                "grant_type": "refresh_token",
                "client_id": "android",
                "scope": "client",
            })
            self.assertEqual(call["headers"], {"Accept": "application/json"})
            self.assertNotIn("hardware_id", call["form"])
            self.assertEqual(refreshed["access_token"], "access")
            self.assertEqual(refreshed["refresh_token"], "refresh-2")
            self.assertEqual((data_dir / "blink-auth.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(read_json(data_dir / "blink-auth.json")["oauth_client_id"], "android")

    def test_client_update_uses_blink_host_root_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            (data_dir / "fcm-state.json").write_text(json.dumps({
                "status": "ready",
                "fcm_token": "test-fcm-token",
            }))
            (data_dir / "blink-auth.json").write_text(json.dumps({
                "oauth_client_id": "android",
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "expires_at": int(time.time()) + 3600,
                "tier": "test-tier",
                "account_id": "123",
            }))
            with patch.object(
                blink_account,
                "_request",
                side_effect=[
                    (200, {"Client-Id": "456"}, b"{}"),
                    (200, {}, b"{}"),
                ],
            ) as request:
                associate_fcm_token(data_dir)

        update_call = request.call_args_list[1]
        self.assertEqual(
            update_call.args[1],
            "https://rest-test-tier.immedia-semi.com/clients/456/update",
        )
        self.assertEqual(update_call.kwargs["body"]["notification_key"], "test-fcm-token")
        self.assertEqual(update_call.kwargs["headers"]["Client-Id"], "456")


if __name__ == "__main__":
    unittest.main()
