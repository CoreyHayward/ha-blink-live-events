# Blink push protocol notes

This document records protocol findings used by the receiver. Blink may change the Android app and backend at any time. The integration is community-maintained and is not affiliated with Blink, Amazon, Google, or Home Assistant.

## Findings

- The Blink Android app uses Firebase Cloud Messaging (FCM) and a separate Blink client association request. A public FCM sender ID alone is insufficient to register a receiver.
- Blink associates the FCM registration with a client through its client update API, which includes a notification key. The receiver uses a separate Blink client ID and session; it does not reuse an existing BlinkPy, Home Assistant, or live-view proxy session.
- Current Android app notification handling maps `category=media,event_type=button_press` to a doorbell press. It maps `category=motion,event_type=cloud_motion` or `cam2sm_motion` to motion.
- Blink may request a notification receipt. When the associated transaction and tier fields are present, the receiver sends the requested acknowledgement.
- Pushes are received over Google's Mobile Connection Server (MCS) transport. The receiver responds to server heartbeats, saves messages before acknowledging the stream, and resumes using recent persistent IDs.

The historical [BlinkPy discussion #770](https://github.com/fronzbot/blinkpy/discussions/770) is useful background but does not demonstrate a working Blink push listener. BlinkPy's normal HA integration discovers events by polling; this receiver uses the direct FCM connection.

## Validation summary

Real physical doorbell presses and separate camera motion-only activity were matched to direct FCM pushes. Doorbell and motion messages were acknowledged when requested, forwarded to HA, and observed by HA automations. This established that the event path works without polling a camera media list or waiting for a clip.

Validation is evidence for the tested Blink app/backend version, not a guarantee of permanent compatibility. FCM token renewal and re-association after token rotation remain manual. The production receiver should be monitored and revalidated after Blink Android app updates.

## Implementation references

- [Firebase Android FCM setup guide](https://firebase.google.com/docs/cloud-messaging/android/get-started) explains app registration and token lifecycle.
- [Home Assistant event entity documentation](https://developers.home-assistant.io/docs/core/entity/event/) describes entities for one-time physical events.
- MCS protocol behavior was compared with [Chromium's MCS client](https://chromium.googlesource.com/chromium/src/+/aec27a9d1bcacb8c0b432a301ac27aadd4aa050d/google_apis/gcm/engine/mcs_client.cc) and [microG's MCS service](https://github.com/microg/GmsCore/blob/master/play-services-core/src/main/java/org/microg/gms/gcm/McsService.java).
- MCS client files in `receiver/vendor/fcm_receiver` are based on [`agusibrahim/pyfcm-receiver`](https://github.com/agusibrahim/pyfcm-receiver/tree/087f61b34b3cea806a75b449b6272e11169d025a), commit `087f61b34b3cea806a75b449b6272e11169d025a`; its MIT license is retained alongside the vendored code.
