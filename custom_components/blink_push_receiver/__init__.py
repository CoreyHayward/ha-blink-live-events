"""Home Assistant integration for Blink Live Events."""

from __future__ import annotations

from dataclasses import dataclass

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, EVENT_TYPE
from .event_data import normalize_event

PLATFORMS: tuple[Platform, ...] = (Platform.EVENT,)


@dataclass
class BlinkPushReceiverRuntimeData:
    """Runtime data for the receiver integration."""

    webhook_id: str


type BlinkPushReceiverConfigEntry = ConfigEntry[BlinkPushReceiverRuntimeData]


async def _async_handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response:
    """Validate a receiver event, then publish it on the HA event bus."""
    try:
        body = await request.json()
    except ValueError:
        return web.Response(
            status=web.HTTPBadRequest.status_code, text="Expected a JSON event"
        )

    if not isinstance(body, dict):
        return web.Response(
            status=web.HTTPBadRequest.status_code, text="Expected a JSON object"
        )

    event_data = normalize_event(body)
    if event_data is None:
        return web.Response(
            status=web.HTTPBadRequest.status_code,
            text="Unsupported or invalid Blink event",
        )

    hass.bus.async_fire(EVENT_TYPE, event_data)
    return web.Response(status=web.HTTPNoContent.status_code)


async def async_setup_entry(
    hass: HomeAssistant, entry: BlinkPushReceiverConfigEntry
) -> bool:
    """Register the local webhook and event entity platform."""
    webhook_id = entry.options.get("webhook_id") or entry.data["webhook_id"]
    entry.runtime_data = BlinkPushReceiverRuntimeData(webhook_id=webhook_id)

    webhook.async_register(
        hass,
        DOMAIN,
        "Blink Live Events",
        webhook_id,
        _async_handle_webhook,
        allowed_methods=["POST"],
        local_only=True,
    )

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        webhook.async_unregister(hass, webhook_id)
        raise
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BlinkPushReceiverConfigEntry
) -> bool:
    """Unload entities and unregister the webhook."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    webhook.async_unregister(hass, entry.runtime_data.webhook_id)
    return True


async def async_reload_entry(
    hass: HomeAssistant, entry: BlinkPushReceiverConfigEntry
) -> None:
    """Reload after the receiver URL options change."""
    await hass.config_entries.async_reload(entry.entry_id)
