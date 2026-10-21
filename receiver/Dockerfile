FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/CoreyHayward/blink-push-receiver" \
      org.opencontainers.image.description="Blink cloud push receiver with Home Assistant event delivery" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BLINK_PUSH_DATA_DIR=/data

WORKDIR /opt
ARG BLINK_PUSH_UID=1000
ARG BLINK_PUSH_GID=1000
RUN groupadd --gid ${BLINK_PUSH_GID} blinkpush \
    && useradd --uid ${BLINK_PUSH_UID} --gid ${BLINK_PUSH_GID} --no-create-home --shell /usr/sbin/nologin blinkpush \
    && mkdir -p /data \
    && chown ${BLINK_PUSH_UID}:${BLINK_PUSH_GID} /data
COPY receiver/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY receiver /opt/receiver
RUN chmod -R a+rX /opt/receiver

USER ${BLINK_PUSH_UID}:${BLINK_PUSH_GID}
ENTRYPOINT ["python", "-m", "receiver.blink_push_receiver"]
