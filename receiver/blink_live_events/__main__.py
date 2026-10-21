from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .blink_account import BlinkAccountError, associate_fcm_token
from .daemon import listen
from .fcm_registration import register_fcm
from .summarize import summarize


def _default_data_dir() -> Path:
    return Path(os.environ.get("BLINK_LIVE_EVENTS_DATA_DIR", "/data"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Blink Live Events Android FCM listener")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_default_data_dir(),
        help="private persistent state directory (default: /data)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    register_fcm_parser = commands.add_parser("register-fcm", help="create the independent Android FCM identity")
    register_fcm_parser.add_argument(
        "--firebase-config",
        type=Path,
        default=None,
        help="optional JSON overrides for the bundled Blink Android Firebase config",
    )
    commands.add_parser("register-blink", help="sign in through Blink's hosted page and associate this receiver")
    listen_parser = commands.add_parser("listen", help="maintain the MCS connection and capture pushes")
    listen_parser.add_argument("--heartbeat-seconds", type=int, default=600)
    commands.add_parser("summarize", help="print captured events without private IDs or raw payloads")

    args = parser.parse_args()
    args.data_dir = args.data_dir.expanduser().resolve()
    try:
        if args.command == "register-fcm":
            firebase_config = (
                args.firebase_config.expanduser().resolve()
                if args.firebase_config is not None
                else None
            )
            state_path = register_fcm(firebase_config, args.data_dir)
            print(f"Independent Android FCM identity is ready; private state: {state_path}")
            return 0
        if args.command == "register-blink":
            auth_path = associate_fcm_token(args.data_dir)
            print(f"Blink client association completed; private state: {auth_path}")
            return 0
        if args.command == "listen":
            if args.heartbeat_seconds < 60:
                parser.error("--heartbeat-seconds must be at least 60")
            listen(args.data_dir, args.heartbeat_seconds)
            return 0
        if args.command == "summarize":
            summarize(args.data_dir)
            return 0
        return 2
    except BlinkAccountError as error:
        print(f"Blink Live Events: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
