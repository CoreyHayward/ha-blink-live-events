"""Event entities for Blink doorbell presses and camera motion."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.event import (
    DoorbellEventType,
    EventDeviceClass,
    EventEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CLASSIFICATION_DOORBELL,
    CLASSIFICATION_MOTION,
    DOMAIN,
    EVENT_TYPE,
)


def _entity_event_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """Expose stable event details without replacing HA's event_type field."""
    attributes = {
        key: value
        for key, value in data.items()
        if key not in {"event_type", "ha_event_type", "schema_version", "source"}
    }
    if "event_type" in data:
        attributes["blink_event_type"] = data["event_type"]
    return attributes


class BlinkPushEvent(EventEntity):
    """Base event entity that listens for one receiver classification."""

    _classification: str
    _ha_event_type: str

    def __init__(self, entry_id: str, classification: str) -> None:
        """Initialize an event entity."""
        self._classification = classification
        self._attr_unique_id = f"{entry_id}_{classification}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Blink Push Receiver",
            manufacturer="Blink Push Receiver community project",
            model="FCM event bridge",
        )

    async def async_added_to_hass(self) -> None:
        """Listen for receiver events after the entity is added."""
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_TYPE, self._handle_receiver_event)
        )

    @callback
    def _handle_receiver_event(self, event: Event) -> None:
        """Publish the matching Blink event to this HA event entity."""
        data = event.data
        if data.get("classification") != self._classification:
            return

        self._trigger_event(
            self._ha_event_type,
            _entity_event_attributes(data),
        )
        self.async_write_ha_state()


class BlinkDoorbellEvent(BlinkPushEvent):
    """Doorbell presses from Blink doorbells."""

    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types: ClassVar[list[str]] = [DoorbellEventType.RING]
    _attr_translation_key = "doorbell"
    _classification = CLASSIFICATION_DOORBELL
    _ha_event_type = DoorbellEventType.RING


class BlinkMotionEvent(BlinkPushEvent):
    """Motion events from Blink cameras."""

    _attr_device_class = EventDeviceClass.MOTION
    _attr_event_types: ClassVar[list[str]] = ["motion"]
    _attr_translation_key = "camera_motion"
    _classification = CLASSIFICATION_MOTION
    _ha_event_type = "motion"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the two event entities supported by the receiver."""
    async_add_entities(
        [
            BlinkDoorbellEvent(entry.entry_id, CLASSIFICATION_DOORBELL),
            BlinkMotionEvent(entry.entry_id, CLASSIFICATION_MOTION),
        ]
    )
