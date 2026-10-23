"""Tests for Blink Live Events' Home Assistant event contract."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from homeassistant.core import Event
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blink_live_events.const import DOMAIN, EVENT_TYPE
from receiver.blink_live_events.capture import MessageCapture
from receiver.blink_live_events.ha_delivery import build_ha_event
from receiver.vendor.fcm_receiver.messages_manual import AppData, DataMessageStanza

WEBHOOK_ID = "blink-live-events-test-secret"


@pytest.fixture
def config_entry(hass):
    """Add the integration config entry to the test instance."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Blink Live Events",
        data={"webhook_id": WEBHOOK_ID},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    return entry


async def test_webhook_publishes_sanitized_event_and_updates_entities(
    hass, hass_client, config_entry
):
    """Valid pushes reach the bus and native event entities."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = {
        entity.unique_id: entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }
    doorbell_entity = entities[f"{config_entry.entry_id}_doorbell_press"]
    motion_entity = entities[f"{config_entry.entry_id}_camera_motion"]

    received: list[Event] = []
    hass.bus.async_listen(EVENT_TYPE, received.append)
    client = await hass_client()
    response = await client.post(
        f"/api/webhook/{WEBHOOK_ID}",
        json={
            "schema_version": 1,
            "source": "blink_live_events",
            "event_id": "safe-event-hash",
            "classification": "doorbell_press",
            "category": "media",
            "event_type": "button_press",
            "provider_timestamp": "2026-01-01T12:00:00.000Z",
            "received_at": "2026-01-01T12:00:00.040Z",
            "account_id": "must-not-be-forwarded",
            "raw_payload": {"private": "must-not-be-forwarded"},
        },
    )
    await hass.async_block_till_done()

    assert response.status == 204
    assert len(received) == 1
    assert received[0].data == {
        "schema_version": 1,
        "source": DOMAIN,
        "event_id": "safe-event-hash",
        "classification": "doorbell_press",
        "category": "media",
        "event_type": "button_press",
        "provider_timestamp": "2026-01-01T12:00:00.000Z",
        "received_at": "2026-01-01T12:00:00.040Z",
        "ha_event_type": "ring",
    }
    assert "account_id" not in received[0].data
    assert "raw_payload" not in received[0].data

    doorbell_state = hass.states.get(doorbell_entity)
    assert doorbell_state is not None
    assert doorbell_state.attributes["event_type"] == "ring"
    assert doorbell_state.attributes["classification"] == "doorbell_press"
    assert doorbell_state.attributes["blink_event_type"] == "button_press"

    motion_response = await client.post(
        f"/api/webhook/{WEBHOOK_ID}",
        json={
            "event_id": "safe-motion-hash",
            "classification": "camera_motion",
            "category": "motion",
            "event_type": "cam2sm_motion",
            "camera_name": "Test camera",
            "received_at": "2026-01-01T12:02:00.040Z",
        },
    )
    await hass.async_block_till_done()

    assert motion_response.status == 204
    assert len(received) == 2
    motion_state = hass.states.get(motion_entity)
    assert motion_state is not None
    assert motion_state.attributes["event_type"] == "motion"
    assert motion_state.attributes["camera_name"] == "Test camera"
    assert motion_state.attributes["blink_event_type"] == "cam2sm_motion"


async def test_webhook_rejects_unrecognized_or_incomplete_events(
    hass, hass_client, config_entry
):
    """The webhook rejects unexpected event classes and missing event IDs."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    client = await hass_client()
    received: list[Event] = []
    hass.bus.async_listen(EVENT_TYPE, received.append)

    response = await client.post(
        f"/api/webhook/{WEBHOOK_ID}",
        json={"event_id": "x", "classification": "unknown"},
    )
    incomplete_response = await client.post(
        f"/api/webhook/{WEBHOOK_ID}",
        json={"classification": "camera_motion"},
    )
    unsupported_version_response = await client.post(
        f"/api/webhook/{WEBHOOK_ID}",
        json={
            "schema_version": 2,
            "event_id": "future-event",
            "classification": "camera_motion",
        },
    )
    missing_generic_type_response = await client.post(
        f"/api/webhook/{WEBHOOK_ID}",
        json={"event_id": "generic-without-type", "classification": "other"},
    )
    await hass.async_block_till_done()

    assert response.status == 400
    assert incomplete_response.status == 400
    assert unsupported_version_response.status == 400
    assert missing_generic_type_response.status == 400
    assert received == []


async def test_webhook_accepts_new_event_types_without_creating_native_entity(
    hass, hass_client, config_entry
):
    """New Blink events reach the bus without needing a device allowlist."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    received: list[Event] = []
    hass.bus.async_listen(EVENT_TYPE, received.append)
    client = await hass_client()
    response = await client.post(
        f"/api/webhook/{WEBHOOK_ID}",
        json={
            "event_id": "new-event-hash",
            "classification": "other",
            "category": "future_category",
            "event_type": "new_sensor_activity",
            "camera_name": "Unlisted camera model",
        },
    )
    minimal_response = await client.post(
        f"/api/webhook/{WEBHOOK_ID}",
        json={
            "event_id": "minimal-new-event-hash",
            "classification": "other",
            "event_type": "new_sensor_activity",
        },
    )
    await hass.async_block_till_done()

    assert response.status == 204
    assert minimal_response.status == 204
    assert len(received) == 2
    assert received[0].data == {
        "schema_version": 1,
        "source": DOMAIN,
        "event_id": "new-event-hash",
        "classification": "other",
        "category": "future_category",
        "event_type": "new_sensor_activity",
        "camera_name": "Unlisted camera model",
    }
    assert received[1].data == {
        "schema_version": 1,
        "source": DOMAIN,
        "event_id": "minimal-new-event-hash",
        "classification": "other",
        "event_type": "new_sensor_activity",
    }
    assert len(entities) == 2


@pytest.mark.parametrize(
    ("category", "event_type"),
    [
        ("motion", "cam2sm_motion"),
        ("motion", "cloud_motion"),
        ("media", "pir"),
        ("media", "cv_motion"),
    ],
)
async def test_receiver_generated_motion_event_reaches_ha(
    hass, hass_client, config_entry, tmp_path, category, event_type
):
    """Received motion pushes trigger the HA motion entity."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = {
        entity.unique_id: entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }
    motion_entity = entities[f"{config_entry.entry_id}_camera_motion"]
    received: list[Event] = []
    hass.bus.async_listen(EVENT_TYPE, received.append)
    client = await hass_client()

    capture = MessageCapture(tmp_path)
    capture.state_path.write_text("{}", encoding="utf-8")
    capture.handle(
        DataMessageStanza(
            id="private-message-id",
            persistent_id="private-fcm-id",
            sent=1767268800200,
            category=category,
            app_data=[
                AppData("event_type", event_type),
                AppData("camera_name", "Test camera"),
                AppData("unique_id", "private-blink-transaction-id"),
            ],
        ),
        SimpleNamespace(persistent_ids=[]),
    )
    record = json.loads(capture.events_path.read_text().splitlines()[0])
    receiver_payload = build_ha_event(record)
    response = await client.post(f"/api/webhook/{WEBHOOK_ID}", json=receiver_payload)
    await hass.async_block_till_done()

    assert response.status == 204
    assert len(received) == 1
    assert received[0].data["schema_version"] == 1
    assert received[0].data["source"] == DOMAIN
    assert received[0].data["event_id"] == receiver_payload["event_id"]
    assert received[0].data["classification"] == "camera_motion"
    assert received[0].data["category"] == category
    assert received[0].data["event_type"] == event_type
    assert received[0].data["ha_event_type"] == "motion"
    assert received[0].data["provider_timestamp"] == "2026-01-01T12:00:00.200Z"
    assert "private-fcm-id" not in str(received[0].data)
    assert "private-message-id" not in str(received[0].data)
    assert "private-blink-transaction-id" not in str(received[0].data)

    motion_state = hass.states.get(motion_entity)
    assert motion_state is not None
    assert motion_state.attributes["event_type"] == "motion"
    assert motion_state.attributes["camera_name"] == "Test camera"
    assert motion_state.attributes["blink_event_type"] == event_type


async def test_setup_generates_a_private_webhook_id(hass):
    """The config flow stores a newly generated webhook identifier."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )

    assert result["type"] == "create_entry"
    webhook_id = result["data"]["webhook_id"]
    assert isinstance(webhook_id, str)
    assert len(webhook_id) >= 48
    assert webhook_id != WEBHOOK_ID


async def test_options_show_and_rotate_receiver_url(hass, hass_client, config_entry):
    """The options flow exposes the URL and switches to a new secret on rotation."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)

    flow = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert flow["type"] == "menu"
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], user_input={"next_step_id": "webhook"}
    )
    assert flow["type"] == "form"
    assert (
        f"/api/webhook/{WEBHOOK_ID}" in flow["description_placeholders"]["webhook_url"]
    )
    await hass.config_entries.options.async_configure(flow["flow_id"], user_input={})

    flow = await hass.config_entries.options.async_init(config_entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], user_input={"next_step_id": "rotate_webhook"}
    )
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], user_input={}
    )
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    new_webhook_id = config_entry.options["webhook_id"]
    assert new_webhook_id != WEBHOOK_ID
    client = await hass_client()
    response = await client.post(
        f"/api/webhook/{new_webhook_id}",
        json={
            "event_id": "rotated-secret-test",
            "classification": "doorbell_press",
        },
    )
    assert response.status == 204
