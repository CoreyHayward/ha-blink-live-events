FROM python:3.12-slim

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
COPY receiver /opt/receiver
RUN chmod -R a+rX /opt/receiver \
    && python -m pip install --no-cache-dir -r /opt/receiver/requirements.txt

USER ${BLINK_PUSH_UID}:${BLINK_PUSH_GID}
ENTRYPOINT ["python", "-m", "receiver.blink_push_receiver"]
