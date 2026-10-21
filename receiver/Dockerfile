FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/CoreyHayward/ha-blink-live-events" \
      org.opencontainers.image.description="Real-time Blink push events for Home Assistant" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BLINK_LIVE_EVENTS_DATA_DIR=/data

WORKDIR /opt
ARG BLINK_LIVE_EVENTS_UID=1000
ARG BLINK_LIVE_EVENTS_GID=1000
RUN groupadd --gid ${BLINK_LIVE_EVENTS_GID} blinkliveevents \
    && useradd --uid ${BLINK_LIVE_EVENTS_UID} --gid ${BLINK_LIVE_EVENTS_GID} --no-create-home --shell /usr/sbin/nologin blinkliveevents \
    && mkdir -p /data \
    && chown ${BLINK_LIVE_EVENTS_UID}:${BLINK_LIVE_EVENTS_GID} /data
COPY receiver/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY receiver /opt/receiver
RUN chmod -R a+rX /opt/receiver

USER ${BLINK_LIVE_EVENTS_UID}:${BLINK_LIVE_EVENTS_GID}
ENTRYPOINT ["python", "-m", "receiver.blink_live_events"]
