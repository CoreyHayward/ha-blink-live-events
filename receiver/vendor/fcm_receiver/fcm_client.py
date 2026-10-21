from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from typing import Callable, List, Optional, Tuple, Dict

try:
    from .crypto_utils import (
        b64url_no_pad,
        create_keys,
        decode_private_key_der_b64,
        encode_private_key_der_b64,
        public_key_bytes_uncompressed,
        decrypt_message_webpush,
    )
except ImportError:  # Android MCS does not need Web Push crypto keys.
    b64url_no_pad = None
    create_keys = None
    decode_private_key_der_b64 = None
    encode_private_key_der_b64 = None
    public_key_bytes_uncompressed = None
    decrypt_message_webpush = None
from .fcm_socket import (
    FCMSocketHandler,
    dial_fcm,
    KMCS_VERSION,
    K_LOGIN_REQUEST,
)
from .http_client import (
    send_gcm_checkin_request,
    send_gcm_register_request,
    send_fcm_install_request,
    send_fcm_register_request,
    send_topic_subscription_request,
)
from .messages_manual import (
    LoginRequest,
    Setting,
)
from .marshal_manual import marshal_login_request
from .proto_manual import put_uvarint


DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 28
TOPIC_PREFIX = "/topics/"
TOPIC_VALID_RE = re.compile(r"^[A-Za-z0-9\-_.~%]{1,900}$")


class FCMClient:
    def __init__(self) -> None:
        self.vapid_key: Optional[str] = None
        self.api_key: str = ""
        self.app_id: str = ""
        self.project_id: str = ""
        self.client_id: Optional[str] = None
        self.gcm_token: str = ""
        self.fcm_token: str = ""
        self.android_id: int = 0
        self.security_token: int = 0
        self.private_key = None
        self.public_key = None
        self.auth_secret: Optional[bytes] = None
        self.persistent_ids: List[str] = []
        self.heartbeat_interval_sec: int = 600
        # Control whether to perform GCM register3 to obtain gcmToken
        # This is required for the current web registration path to obtain an FCM token.
        # Set to False only if you already have tokens persisted and just want to listen.
        self.require_gcm_token: bool = True
        self.on_data_message: Optional[Callable[[bytes, str], None]] = None
        self.on_raw_message: Optional[Callable[[object, str], None]] = None
        self.on_notification_message: Optional[Callable[[dict, str], None]] = None
        self.on_connection_status: Optional[Callable[[str, str], None]] = None
        self.on_tag: Optional[Callable[[int, str, str], None]] = None

        self._socket = FCMSocketHandler()
        self._socket.on_message = self._on_message
        self._socket.on_close = self._on_socket_close
        self._socket.on_tag = self._on_tag_internal
        self._stop = threading.Event()
        self._reconnect_lock = threading.Lock()
        self._reconnector: Optional[threading.Thread] = None

    # Key helpers
    def create_new_keys(self) -> Tuple[str, str]:
        if create_keys is None or encode_private_key_der_b64 is None:
            raise RuntimeError("cryptography is required for Web Push key generation")
        priv, pub, auth = create_keys()
        self.private_key = priv
        self.public_key = pub
        self.auth_secret = auth
        priv_b64 = encode_private_key_der_b64(priv)
        auth_b64 = base64.b64encode(auth).decode()
        return priv_b64, auth_b64

    def load_keys(self, private_key_base64: str, auth_secret_base64: str) -> None:
        if decode_private_key_der_b64 is None:
            raise RuntimeError("cryptography is required for Web Push key loading")
        self.private_key = decode_private_key_der_b64(private_key_base64)
        self.public_key = self.private_key.public_key() if self.private_key else None
        self.auth_secret = base64.b64decode(auth_secret_base64)

    # Registration flow (for new device)
    def register(self) -> Tuple[str, str, int, int]:
        if not (self.app_id and self.project_id and self.api_key):
            raise RuntimeError("FCMClient requires AppId, ProjectID, ApiKey")

        if not (self.android_id and self.security_token):
            # GCM Checkin (Android ID + Security Token)
            req = self._build_checkin_request()
            self.android_id, self.security_token = send_gcm_checkin_request(req)
            print("[fcm_client] Android check-in completed")

        if not (self.private_key and self.auth_secret is not None):
            raise RuntimeError("client private key not set. Call load_keys() or create_new_keys().")

        if self.require_gcm_token and not self.gcm_token:
            # GCM register token (retry like Go: handles PHONE_REGISTRATION_ERROR)
            attempts = 0
            last_err: Optional[Exception] = None
            while attempts < 10 and not self.gcm_token:
                attempts += 1
                try:
                    self.gcm_token = send_gcm_register_request(
                        android_id=self.android_id,
                        security_token=self.security_token,
                        app_id=self.app_id,
                    )
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1)
            if not self.gcm_token:
                raise RuntimeError(f"failed to send GCM register request: {last_err}")
            print("[fcm_client] GCM registration completed")

        # FCM: obtain FCM token only if needed and possible
        if not self.fcm_token:
            if not self.require_gcm_token and not self.gcm_token:
                # User opted to skip GCM register; cannot register FCM without gcm endpoint.
                # Proceed without FCM token (listening still works with AndroidId/SecurityToken).
                print("[fcm_client] skipping FCM register (no gcm token, require_gcm_token=False)")
            else:
                # installation auth token
                installation_token = send_fcm_install_request(self.api_key, self.project_id, self.app_id, android=False)
                print("[fcm_client] Firebase installation authorization completed")

                # register to get FCM token
                pub_bytes = public_key_bytes_uncompressed(self.public_key)
                pub_b64url = b64url_no_pad(pub_bytes)
                auth_b64url = b64url_no_pad(self.auth_secret)
                self.fcm_token = send_fcm_register_request(
                    api_key=self.api_key,
                    project_id=self.project_id,
                    gcm_token=self.gcm_token,
                    p256dh_public_key_b64url=pub_b64url,
                    auth_secret_b64url=auth_b64url,
                    installation_auth_token=installation_token,
                )
                print("[fcm_client] FCM registration completed")
        return self.fcm_token, self.gcm_token, self.android_id, self.security_token

    # Topic operations
    @staticmethod
    def normalize_topic(topic: str) -> str:
        if not topic:
            raise ValueError("topic name is required")
        topic = topic.strip()
        if topic.startswith(TOPIC_PREFIX):
            topic_name = topic[len(TOPIC_PREFIX) :]
        else:
            topic_name = topic
        if not TOPIC_VALID_RE.fullmatch(topic_name):
            raise ValueError(
                "topic must match [a-zA-Z0-9-_.~%]{1,900}"
            )
        return f"{TOPIC_PREFIX}{topic_name}"

    def subscribe_to_topic(self, topic: str) -> dict:
        if not (self.android_id and self.security_token):
            raise RuntimeError("android credentials not initialized; call register() first")
        if not self.fcm_token:
            raise RuntimeError("fcm_token is required; ensure register() has been called")
        topic_path = self.normalize_topic(topic)
        result = send_topic_subscription_request(
            android_id=self.android_id,
            security_token=self.security_token,
            fcm_token=self.fcm_token,
            topic_path=topic_path,
            app="org.chromium.linux",
            app_ver="1",
            app_ver_name="1",
            gms_app_id=self.app_id or None,
            delete=False,
        )
        return result

    def unsubscribe_from_topic(self, topic: str) -> dict:
        topic_path = self.normalize_topic(topic)
        result = send_topic_subscription_request(
            android_id=self.android_id,
            security_token=self.security_token,
            fcm_token=self.fcm_token,
            topic_path=topic_path,
            app="org.chromium.linux",
            app_ver="1",
            app_ver_name="1",
            gms_app_id=self.app_id or None,
            delete=True,
        )
        return result

    def start_listening(self) -> None:
        if not (self.android_id and self.security_token):
            raise RuntimeError("AndroidId/SecurityToken not set. Call register() first.")
        self._set_status("connecting")
        self._connect_and_start()

    def close(self) -> None:
        self._stop.set()
        self._socket.close()

    # Internals
    def _build_checkin_request(self):
        from .messages_manual import (
            AndroidCheckinRequest,
            AndroidCheckinProto,
            ChromeBuildProto,
            DeviceType,
            ChromePlatform,
            ChromeChannel,
        )

        chrome = ChromeBuildProto(
            platform=ChromePlatform.PLATFORM_LINUX,
            chrome_version="chrome-63.0.3234.0",
            channel=ChromeChannel.CHANNEL_STABLE,
        )
        checkin = AndroidCheckinProto(
            type=DeviceType.DEVICE_CHROME_BROWSER,
            chrome_build=chrome,
        )
        req = AndroidCheckinRequest(
            id=self.android_id,
            digest="2-7-153-0-1-0-0-0",
            checkin=checkin,
            version=3,
            security_token=self.security_token or None,
        )
        return req

    def _build_login_request_packet(self) -> bytes:
        # Mirrors go CreateLoginRequestRaw: manual login request + framing (version, tag, size)
        android_id_str = str(self.android_id)
        android_hex = "android-" + format(self.android_id, "x")
        security_token_str = str(self.security_token)
        setting = [Setting(name="new_vc", value="1")]

        req = LoginRequest(
            id="chrome-63.0.3234.0",
            domain="mcs.android.com",
            user=android_id_str,
            resource=android_id_str,
            auth_token=security_token_str,
            device_id=android_hex,
            setting=setting,
            received_persistent_id=self.persistent_ids[-1000:],
            adaptive_heartbeat=False,
            use_rmq2=True,
            auth_service=2,  # ANDROID_ID
            network_type=1,
        )
        payload = marshal_login_request(req)
        size = len(payload)
        # Framing: version, tag, size (varint), payload
        framed = bytearray()
        framed.append(KMCS_VERSION)
        framed.append(K_LOGIN_REQUEST)
        framed.extend(put_uvarint(size))
        framed.extend(payload)
        return bytes(framed)

    def _on_message(self, tag: int, message_obj: object) -> None:
        # Heartbeat ping is handled at socket level. Handle data messages
        from .messages_manual import DataMessageStanza

        if tag == 0:  # HEARTBEAT_PING seen
            # Rely on on_tag callback for heartbeat visibility
            return
        if tag == 3:  # Login response
            error = getattr(message_obj, "error", None)
            if error is not None and getattr(error, "code", 0):
                self._set_status("login_failed")
                self._stop.set()
                self._socket.close()
                return
            heartbeat = getattr(message_obj, "heartbeat_config", None)
            interval_ms = getattr(heartbeat, "interval_ms", None)
            if isinstance(interval_ms, int) and interval_ms > 0:
                self.heartbeat_interval_sec = max(1, interval_ms // 1000)
                self._socket.heartbeat_interval_sec = self.heartbeat_interval_sec
            self._set_status("connected")
            return
        if tag == 8 and isinstance(message_obj, DataMessageStanza):
            self._on_data_message(message_obj)

    def _on_data_message(self, message) -> None:
        def _b64url_decode_no_pad(s: str) -> bytes:
            pad = '=' * (-len(s) % 4)
            return base64.urlsafe_b64decode(s + pad)
        # Deduplicate by persistent_id
        pid = getattr(message, "persistent_id", None)
        if pid and pid not in self.persistent_ids:
            self.persistent_ids.append(pid)
            # TTL cleanup could be implemented with a timer if desired

        identifier = self.client_id or self.project_id or ""

        # Extract encryption parameters if present
        crypto_key = None
        encryption = None
        for ad in message.app_data:
            if ad.key == "crypto-key" and ad.value.startswith("dh="):
                try:
                    crypto_key = _b64url_decode_no_pad(ad.value[3:])
                except Exception as e:
                    print(f"[fcm_client] failed to b64url decode crypto-key: {e}")
            if ad.key == "encryption" and ad.value.startswith("salt="):
                try:
                    encryption = _b64url_decode_no_pad(ad.value[5:])
                except Exception as e:
                    print(f"[fcm_client] failed to b64url decode encryption: {e}")

        if (
            decrypt_message_webpush is not None
            and crypto_key
            and encryption
            and message.raw_data is not None
            and self.auth_secret is not None
        ):
            try:
                pt = decrypt_message_webpush(
                    crypto_key=crypto_key,
                    encryption_salt=encryption,
                    raw_data=message.raw_data,
                    auth_secret=self.auth_secret,
                    private_key=self.private_key,
                )
                # Try to parse JSON for notification callback
                sent_json = False
                if self.on_notification_message:
                    try:
                        obj = json.loads(pt.decode('utf-8'))
                        wrapped = {
                            "payload": obj,
                            "persistentId": getattr(message, "persistent_id", None),
                        }
                        self.on_notification_message(wrapped, identifier)
                        sent_json = True
                    except Exception:
                        sent_json = False
                if not sent_json and self.on_data_message:
                    self.on_data_message(pt, identifier)
                return
            except Exception as e:
                # Fall through to raw handler on decryption failure
                print(f"[fcm_client] decryption failed: {e}")

        if self.on_raw_message:
            self.on_raw_message(message, identifier)

    def _on_socket_close(self, _err: Optional[Exception]) -> None:
        # Trigger auto-reconnect with backoff
        if self._stop.is_set():
            self._set_status("disconnected")
            return
        self._set_status("disconnected")
        with self._reconnect_lock:
            if self._reconnector and self._reconnector.is_alive():
                return
            self._reconnector = threading.Thread(target=self._reconnect_loop, daemon=True)
            self._reconnector.start()

    def _reconnect_loop(self) -> None:
        delay = 1
        while not self._stop.is_set():
            self._set_status("reconnecting")
            try:
                self._connect_and_start()
                return
            except Exception as e:
                print(f"[fcm_client] reconnect failed: {e}; retrying in {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 60)

    def _connect_and_start(self) -> None:
        self._socket.sock = dial_fcm()
        self._socket.is_alive = True
        self._socket.heartbeat_interval_sec = self.heartbeat_interval_sec
        self._socket.init()
        login_packet = self._build_login_request_packet()
        self._socket.send(login_packet)
        print("[fcm_client] login packet sent; starting reader thread")
        self._socket.start()

    def _set_status(self, s: str) -> None:
        if self.on_connection_status:
            try:
                identifier = self.client_id or self.project_id or ""
                self.on_connection_status(s, identifier)
            except Exception:
                pass

    def _on_tag_internal(self, tag: int, name: str) -> None:
        if self.on_tag:
            try:
                identifier = self.client_id or self.project_id or ""
                self.on_tag(tag, name, identifier)
            except Exception:
                pass


class MultiFCMClient:
    """
    Manage multiple FCMClient instances (one per Firebase project),
    start listening concurrently, and proxy callbacks with the provided id.
    """

    def __init__(
        self,
        projects: List[dict],
        credential_dir: str = ".",
        heartbeat_interval_sec: int = 60,
        max_workers: Optional[int] = None,
    ) -> None:
        if not isinstance(projects, list):
            raise ValueError("projects must be provided as a list of dicts")
        for idx, cfg in enumerate(projects):
            if not isinstance(cfg, dict):
                raise ValueError(f"project config at index {idx} must be a dict")
            if "id" not in cfg:
                raise ValueError(f"project config at index {idx} missing required 'id'")
            if cfg["id"] in (None, ""):
                raise ValueError(f"project config at index {idx} has empty 'id'")
            cfg["id"] = str(cfg["id"])
        self.projects = projects
        self.credential_dir = credential_dir
        self.heartbeat_interval_sec = heartbeat_interval_sec
        self.clients: Dict[str, FCMClient] = {}
        self._lock = threading.Lock()
        # Determine worker pool size
        if max_workers is None:
            try:
                # I/O bound workload; allow many workers
                cpu = os.cpu_count() or 4
                self.max_workers = min(32, cpu * 5)
            except Exception:
                self.max_workers = 8
        else:
            self.max_workers = max_workers

        # Multi-level callbacks (same signatures as FCMClient)
        self.on_notification_message: Optional[Callable[[dict, str], None]] = None
        self.on_data_message: Optional[Callable[[bytes, str], None]] = None
        self.on_raw_message: Optional[Callable[[object, str], None]] = None
        self.on_connection_status: Optional[Callable[[str, str], None]] = None
        self.on_tag: Optional[Callable[[int, str, str], None]] = None

    def _cfg_path(self, project_id: str) -> str:
        from pathlib import Path

        return str(Path(self.credential_dir) / f"device_credentials.{project_id}.json")

    def _load_credentials(self, path: str) -> Optional[dict]:
        from pathlib import Path
        import json

        p = Path(path)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        required = ["androidId", "securityToken", "privateKeyBase64", "authSecretBase64"]
        for k in required:
            if k not in data or not data[k]:
                raise RuntimeError("incomplete credentials in json")
        return data

    def _save_credentials(self, path: str, cred: dict) -> None:
        from pathlib import Path
        import json

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cred, indent=2), encoding="utf-8")

    # Proxies to propagate to multi-level callbacks
    def _proxy_notif(self, obj: dict, identifier: str):
        if self.on_notification_message:
            try:
                self.on_notification_message(obj, identifier)
            except Exception:
                pass

    def _proxy_data(self, b: bytes, identifier: str):
        if self.on_data_message:
            try:
                self.on_data_message(b, identifier)
            except Exception:
                pass

    def _proxy_raw(self, o: object, identifier: str):
        if self.on_raw_message:
            try:
                self.on_raw_message(o, identifier)
            except Exception:
                pass

    def _proxy_status(self, s: str, identifier: str):
        if self.on_connection_status:
            try:
                self.on_connection_status(s, identifier)
            except Exception:
                pass

    def _proxy_tag(self, tag: int, name: str, identifier: str):
        if self.on_tag:
            try:
                self.on_tag(tag, name, identifier)
            except Exception:
                pass

    def _prepare_and_start_single(self, cfg: dict) -> Tuple[str, Optional[FCMClient]]:
        identifier = cfg["id"]
        project_id = cfg["project_id"]
        try:
            api_key = cfg["api_key"]
            app_id = cfg["app_id"]

            client = FCMClient()
            client.api_key = api_key
            client.app_id = app_id
            client.project_id = project_id
            client.client_id = identifier
            client.heartbeat_interval_sec = self.heartbeat_interval_sec

            # Wire proxies
            client.on_notification_message = self._proxy_notif
            client.on_data_message = self._proxy_data
            client.on_raw_message = self._proxy_raw
            client.on_connection_status = self._proxy_status
            client.on_tag = self._proxy_tag

            # Load or register credentials
            cfg_path = self._cfg_path(project_id)
            cred = self._load_credentials(cfg_path)
            if cred:
                client.gcm_token = cred.get("gcmToken", "")
                client.fcm_token = cred.get("fcmToken", "")
                client.android_id = int(cred["androidId"]) or 0
                client.security_token = int(cred["securityToken"]) or 0
                client.load_keys(cred["privateKeyBase64"], cred["authSecretBase64"])
            else:
                priv_b64, auth_b64 = client.create_new_keys()
                client.load_keys(priv_b64, auth_b64)
                fcm_token, gcm_token, android_id, security_token = client.register()
                cred = {
                    "apiKey": api_key,
                    "appId": app_id,
                    "projectId": project_id,
                    "fcmToken": fcm_token,
                    "gcmToken": gcm_token,
                    "androidId": android_id,
                    "securityToken": security_token,
                    "privateKeyBase64": priv_b64,
                    "authSecretBase64": auth_b64,
                }
                self._save_credentials(cfg_path, cred)

            # Start listening (each client forks worker threads internally)
            client.start_listening()
            return identifier, client
        except Exception as e:
            print(f"[multi_fcm] failed to start project {project_id} (id={identifier}): {e}")
            return identifier, None

    def start(self) -> None:
        """Create/load all clients and start listening concurrently using a thread pool."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = [ex.submit(self._prepare_and_start_single, cfg) for cfg in self.projects]
            for fut in as_completed(futures):
                identifier, client = fut.result()
                if client is None:
                    continue
                with self._lock:
                    self.clients[identifier] = client

    def close(self) -> None:
        for c in list(self.clients.values()):
            try:
                c.close()
            except Exception:
                pass

    
