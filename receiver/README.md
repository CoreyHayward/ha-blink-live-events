# Standalone receiver

The receiver runs separately from Home Assistant. It keeps an independent Android-style FCM identity, links that identity to a Blink client session, listens for pushes over Google's MCS transport, acknowledges messages when Blink requests a receipt, and forwards supported events to the HA integration.

Read the repository [installation guide](../README.md) first. This file covers the receiver host and registration commands.

## Requirements

- Linux host with Docker Engine and Docker Compose v2; ARM64 and AMD64 are supported by the Python receiver.
- Outbound DNS and internet access, including TCP port 5228 for Google's MCS connection.
- The receiver's bundled Blink Android Firebase client configuration, with optional overrides in `.env`.
- A local-only Home Assistant webhook URL from the integration's Configure screen.

The receiver includes only the four Firebase client values it needs in `firebase-config.default.json`; you do not need to obtain the Blink APK or extract the values. These defaults match Blink Android 60.0 and may need updating if Blink changes its Firebase project. [Firebase describes its Android config as containing unique, non-secret identifiers](https://firebase.google.com/docs/android/google-services-plugin-and-file), and [Firebase API keys identify the project rather than authorize access](https://firebase.google.com/docs/projects/api-keys). The FCM token, Firebase installation credentials, and Blink session remain private per-installation state.

If Blink changes its Firebase values, add only the changed settings to the ignored `.env` file:

```dotenv
BLINK_PUSH_FIREBASE_API_KEY=...
BLINK_PUSH_FIREBASE_APP_ID=...
BLINK_PUSH_FIREBASE_PROJECT_ID=...
BLINK_PUSH_FIREBASE_SENDER_ID=...
```

These environment variables override the corresponding bundled values when creating the FCM identity. Changing them does not modify an identity already stored in the receiver's persistent data volume. Alternatively, supply a JSON file with any values to override by mounting it read-only into the one-shot registration container and passing `--firebase-config /path/in/container`. The JSON keys are `google_api_key`, `google_app_id`, `project_id`, and `gcm_defaultSenderId`.

The optional JSON file is merged over the bundled defaults, then any `.env` overrides are applied. Do not place FCM tokens, Firebase installation credentials, Blink credentials, or Blink session data in this file.

## Build and register

Run these commands from the repository root. Set the Compose user IDs so the service can read the mode-`0600` Firebase file during registration and own its named-volume data:

```sh
cp .env.example .env
chmod 600 .env
export BLINK_PUSH_UID="$(id -u)"
export BLINK_PUSH_GID="$(id -g)"
docker compose -f receiver/compose.yaml build
```

Create the independent FCM identity using the bundled values, or any overrides in `.env`:

```sh
docker compose -f receiver/compose.yaml run --rm blink-push-receiver register-fcm
```

In the integration's **Configure → View receiver URL** screen, copy the private URL into `.env` as `BLINK_PUSH_HA_WEBHOOK_URL`. Keep the URL private. It is a secret capability to publish Blink events to your HA instance.

Then associate the FCM identity with Blink:

```sh
docker compose -f receiver/compose.yaml run --rm -it blink-push-receiver register-blink
```

Open the printed URL in a trusted browser and sign in on Blink's hosted page. Complete verification there, then paste the full callback address into the hidden terminal prompt. The receiver does not ask for or store your Blink password or verification code.

Start the persistent listener:

```sh
docker compose -f receiver/compose.yaml up -d
docker compose -f receiver/compose.yaml logs -f blink-push-receiver
```

`FCM transport connected; waiting for Blink pushes` confirms that Google transport connected. Validate that the separate Blink association is accepted by generating one doorbell press and one motion-only event. A push must arrive from the cloud connection; successful registration alone is not event validation.

## Configuration and privacy

- The bundled Firebase file contains public client identifiers only. The ignored `.env` may contain replacement values; keep it out of commits.
- `.env` is ignored by Git. It contains the HA webhook URL; keep its permissions at `0600`.
- Receiver state is stored in the private Docker volume `receiver_blink-push-data`. It contains FCM and Blink session tokens plus private raw message captures. Protect backups of this volume accordingly.
- The HA payload is allowlisted and omits Blink account IDs, transaction IDs, FCM IDs, and raw push data.
- The Compose service has no published listening ports. It initiates the outbound FCM connection and sends events to HA.
- Change the webhook ID from the integration Configure flow if its URL is exposed, then update `.env` and restart the receiver.

## Current limitations

FCM token renewal and Blink re-association after a token rotation are not automated. The receiver may require FCM and Blink registration again if its independent token is rejected or expires. Blink may also change its app registration or OAuth flows without notice. The implementation has been validated against Blink Android 60.0; check compatibility after Blink app updates.

The receiver does not poll camera media, retrieve clips to detect events, or create camera entities. Existing Blink camera and live-view integrations can continue to run separately.
