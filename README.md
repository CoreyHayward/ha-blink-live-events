# Blink Push Receiver

Receive Blink doorbell presses and camera motion as real-time Home Assistant events. The standalone receiver listens to Blink's cloud push delivery; it does not poll a media list or wait for a clip. A Home Assistant custom integration exposes the events as native event entities and a general event-bus event, so you can decide what automations or integrations to build.

This is a community reverse-engineered project, not an official Blink, Amazon, Google, or Home Assistant product. Blink can change its app and cloud API without notice.

## What you get

- `event.blink_push_receiver_doorbell` for doorbell presses.
- `event.blink_push_receiver_camera_motion` for camera motion.
- The `blink_push_receiver_event` HA event with a sanitized, documented event payload.
- A private, local-only HA webhook endpoint generated during integration setup.
- A standalone Docker Compose receiver for Linux hosts, including ARM64 systems such as Raspberry Pi.

The integration does not install notification automations or require Companion app services. It does not change the official Blink integration, camera entities, or live-view proxies.

## How it works

```mermaid
flowchart LR
    B[Blink cloud] -->|FCM push| R[Standalone receiver]
    R -->|Local-only webhook| H[Home Assistant integration]
    H -->|event entities| E[Your automations]
    H -->|HA event bus| X[Custom integrations, scripts, and other consumers]
```

The receiver holds its own FCM identity and Blink client session. Home Assistant never receives Blink account credentials. The receiver forwards only the event metadata needed for automations; private FCM IDs, Blink account IDs, transaction IDs, and raw push payloads stay in the receiver's private data volume.

## Installation

The custom integration requires Home Assistant 2026.10.0 or newer.

### 1. Install the Home Assistant integration

Once this repository is public, add it in HACS as a custom **Integration** repository, then install **Blink Push Receiver** and restart Home Assistant. HACS requires a public GitHub repository. While this repository is private, install manually: copy `custom_components/blink_push_receiver` into `<config>/custom_components/` and restart HA.

In **Settings → Devices & services → Add integration**, add **Blink Push Receiver**. Open its **Configure** page and select **View receiver URL**. Copy this private URL for the receiver setup. If the URL is exposed, use **Rotate receiver URL** and update the receiver's `.env` file.

### 2. Prepare a receiver host

Use a Linux host with Docker Engine and Docker Compose v2, outbound internet access, and access to your HA local URL. The receiver makes an outbound connection to Google's MCS service (TCP 5228) and sends events to HA. It has no inbound listening port.

Clone the repository on the host that will run the receiver:

```sh
git clone https://github.com/CoreyHayward/blink-push-receiver.git
cd blink-push-receiver
```

Obtain the current Blink Android Firebase values from an authorized copy of the Blink app and place them in `receiver/firebase-config.json` using the required keys shown in the [receiver guide](receiver/README.md). This file is private and is intentionally excluded from Git and the Docker build context. Do not use an old sender ID as a substitute.

### 3. Register Blink and start listening

From the repository root, create the private environment file and set the Compose user IDs:

```sh
cp .env.example .env
chmod 600 .env
export BLINK_PUSH_UID="$(id -u)"
export BLINK_PUSH_GID="$(id -g)"
docker compose -f receiver/compose.yaml build
```

Set `BLINK_PUSH_HA_WEBHOOK_URL` in `.env` to the private URL from the integration's Configure screen. Then create the independent FCM identity and associate it with Blink:

```sh
docker compose -f receiver/compose.yaml run --rm \
  -v "$PWD/receiver/firebase-config.json:/run/secrets/firebase-config.json:ro" \
  blink-push-receiver register-fcm \
  --firebase-config /run/secrets/firebase-config.json

docker compose -f receiver/compose.yaml run --rm -it blink-push-receiver register-blink
```

`register-blink` prints a Blink-hosted sign-in URL. Sign in and complete verification in your browser, then paste the full callback URL into the hidden terminal prompt. Your password and verification code are entered only on Blink's page.

Start the service and follow its logs:

```sh
docker compose -f receiver/compose.yaml up -d
docker compose -f receiver/compose.yaml logs -f blink-push-receiver
```

The listener waits for real Blink pushes. Test one doorbell press and a separate motion-only event to validate your own registration. A connected FCM transport alone does not prove Blink has associated the token.

See [receiver/README.md](receiver/README.md) for registration details, security, and troubleshooting limitations.

## Home Assistant event contract

The integration fires `blink_push_receiver_event` once for every accepted push. Automations, scripts, custom integrations, and event listeners can subscribe to it. Its `event_data` fields are:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer event contract version, initially `1`. |
| `source` | Always `blink_push_receiver`. |
| `event_id` | Stable SHA-256 delivery key used by the receiver to suppress duplicate delivery. |
| `classification` | `doorbell_press` or `camera_motion`. |
| `category` | Blink's notification category when present (`media` or `motion`). |
| `event_type` | Blink's event type, such as `button_press` or `cam2sm_motion`. |
| `ha_event_type` | HA semantic type: `ring` for a doorbell or `motion` for a camera. |
| `camera_name` | Blink camera name for motion events, when included by Blink. |
| `provider_timestamp` | Provider send time in UTC, when present. |
| `created_at` | Blink event timestamp, when present. |
| `received_at` | Receiver UTC receipt timestamp. |

Optional fields may be absent if the Blink push does not include them. The `event_type` field is Blink's raw event type; `ha_event_type` is the stable HA semantic type. Event entity states use `ring` and `motion`, and their attributes contain the allowlisted metadata (with Blink's raw type exposed as `blink_event_type`).

### Build your own automation

One option is to listen to the integration event directly:

```yaml
triggers:
  - trigger: event
    event_type: blink_push_receiver_event
    event_data:
      classification: camera_motion
conditions: []
actions:
  - action: notify.notify
    data:
      title: Blink motion
      message: "{{ trigger.event.data.camera_name or 'A Blink camera' }} detected motion."
```

For a doorbell, set `classification: doorbell_press`. Or automate from the native event entities by selecting one as an event trigger in the HA automation editor. An optional starting point is [`examples/automation-event-bus.yaml`](examples/automation-event-bus.yaml); the integration does not install it.

## Security and limitations

- The HA webhook URL is a secret. HA registers it as local-only; keep the URL and `.env` private and rotate it if exposed.
- Receiver state in the Docker volume includes FCM and Blink session tokens plus private raw-message captures. Protect host backups of that volume.
- The integration and receiver do not send notifications by default.
- FCM token renewal and Blink re-association after rotation are not automated yet. A rejected or expired token may require registration again.
- Blink's app registration and OAuth flow may change. The receiver currently follows the Blink Android 60.0 protocol and needs revalidation after app updates.
- This project receives doorbell and motion events only. It does not provide camera streams or clips; use a separate camera/live-view integration for those.

Protocol notes and validation scope are documented in [BLINK-PUSH-INVESTIGATION.md](BLINK-PUSH-INVESTIGATION.md).

## Development and validation

Run the receiver unit tests with Python 3.12 and its pinned requirements:

```sh
python -m pip install -r receiver/requirements.txt
python -m unittest discover -s receiver/tests -v
```

Run the HA integration tests in a separate Python 3.14 environment because Home Assistant pins an `aiohttp` version that differs from the receiver's BlinkPy dependency:

```sh
python -m pip install -r requirements_test.txt
pytest -q
```

## License

Project code is released under the [MIT License](LICENSE). Vendored files retain the license shipped with their original source.
