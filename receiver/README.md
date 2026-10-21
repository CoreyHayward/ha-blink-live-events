# Standalone receiver

The receiver runs separately from Home Assistant. It keeps an independent Android-style FCM identity, links that identity to a Blink client session, listens for pushes over Google's MCS transport, acknowledges messages when Blink requests a receipt, and forwards supported events to the HA integration.

Read the repository [installation guide](../README.md) first. This file covers the receiver host and registration commands.

## Requirements

- Linux host with Docker Engine and Docker Compose v2; ARM64 and AMD64 are supported by the Python receiver.
- Outbound DNS and internet access, including TCP port 5228 for Google's MCS connection.
- The current Blink Android Firebase configuration values, kept in a local file at `receiver/firebase-config.json`.
- A local-only Home Assistant webhook URL from the integration's Configure screen.

The project does not include or redistribute Blink's Firebase application configuration. Obtain the values from a copy of the current Blink Android app through an authorized source and keep the resulting file private. The required JSON keys are:

```json
{
  "google_api_key": "...",
  "google_app_id": "...",
  "project_id": "...",
  "gcm_defaultSenderId": "..."
}
```

With JADX or an equivalent Android resource viewer, inspect the current Blink Android app resources and search for `google_api_key`, `google_app_id`, `project_id`, and `gcm_defaultSenderId`. Use the matching app values to create the JSON file above. For example, JADX's command-line decoder can unpack a local APK for searching:

```sh
jadx -d /tmp/blink-android-decoded /path/to/your/blink.apk
rg -n 'google_api_key|google_app_id|project_id|gcm_defaultSenderId' /tmp/blink-android-decoded
```

The project does not need the APK after you create the config file. Keep the APK and config outside public commits; `.gitignore` also excludes APK bundles and Firebase config files. Restrict the config file to your account:

```sh
chmod 600 receiver/firebase-config.json
```

Do not substitute a sender ID found in an old forum post. If Blink changes its Android app or Firebase project, registration values may need to be recovered again.

## Build and register

Run these commands from the repository root. Set the Compose user IDs so the service can read the mode-`0600` Firebase file during registration and own its named-volume data:

```sh
cp .env.example .env
chmod 600 .env
export BLINK_PUSH_UID="$(id -u)"
export BLINK_PUSH_GID="$(id -g)"
docker compose -f receiver/compose.yaml build
```

Create the independent FCM identity. The temporary bind mount exposes the Firebase configuration read-only to this one-shot container:

```sh
docker compose -f receiver/compose.yaml run --rm \
  -v "$PWD/receiver/firebase-config.json:/run/secrets/firebase-config.json:ro" \
  blink-push-receiver register-fcm \
  --firebase-config /run/secrets/firebase-config.json
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

- The Firebase file is ignored by Git and excluded from the Docker build context. Do not force-add it.
- `.env` is ignored by Git. It contains the HA webhook URL; keep its permissions at `0600`.
- Receiver state is stored in the private Docker volume `receiver_blink-push-data`. It contains FCM and Blink session tokens plus private raw message captures. Protect backups of this volume accordingly.
- The HA payload is allowlisted and omits Blink account IDs, transaction IDs, FCM IDs, and raw push data.
- The Compose service has no published listening ports. It initiates the outbound FCM connection and sends events to HA.
- Change the webhook ID from the integration Configure flow if its URL is exposed, then update `.env` and restart the receiver.

## Current limitations

FCM token renewal and Blink re-association after a token rotation are not automated. The receiver may require FCM and Blink registration again if its independent token is rejected or expires. Blink may also change its app registration or OAuth flows without notice. The implementation has been validated against Blink Android 60.0; check compatibility after Blink app updates.

The receiver does not poll camera media, retrieve clips to detect events, or create camera entities. Existing Blink camera and live-view integrations can continue to run separately.
