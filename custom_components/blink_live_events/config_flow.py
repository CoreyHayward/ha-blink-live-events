"""Config and options flows for Blink Live Events."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import webhook
from homeassistant.core import callback
from homeassistant.helpers.network import NoURLAvailableError

from .const import DOMAIN


class BlinkLiveEventsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up a private webhook for a standalone receiver."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Create an integration entry and its random webhook ID."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="Blink Live Events",
                data={"webhook_id": webhook.async_generate_id()},
            )

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: config_entries.ConfigEntry,
    ) -> BlinkLiveEventsOptionsFlow:
        """Return the options flow."""
        return BlinkLiveEventsOptionsFlow()


class BlinkLiveEventsOptionsFlow(config_entries.OptionsFlow):
    """Show the webhook URL or rotate its secret identifier."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Offer webhook setup and secret rotation."""
        return self.async_show_menu(
            step_id="init", menu_options=["webhook", "rotate_webhook"]
        )

    async def async_step_webhook(self, user_input: dict[str, Any] | None = None) -> Any:
        """Display the private webhook URL for receiver configuration."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        webhook_id = (
            self.config_entry.options.get("webhook_id")
            or self.config_entry.data["webhook_id"]
        )
        try:
            webhook_url = webhook.async_generate_url(
                self.hass,
                webhook_id,
                allow_internal=True,
                allow_external=False,
                prefer_external=False,
            )
        except NoURLAvailableError:
            return self.async_show_form(
                step_id="webhook",
                data_schema=vol.Schema({}),
                errors={"base": "set_internal_url"},
            )

        return self.async_show_form(
            step_id="webhook",
            data_schema=vol.Schema({}),
            description_placeholders={"webhook_url": webhook_url},
        )

    async def async_step_rotate_webhook(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Replace the webhook ID with a newly generated secret."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={"webhook_id": webhook.async_generate_id()},
            )

        return self.async_show_form(
            step_id="rotate_webhook", data_schema=vol.Schema({})
        )
