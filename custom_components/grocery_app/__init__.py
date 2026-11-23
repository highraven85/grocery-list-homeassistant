"""The Grocery App integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GroceryAppClient
from .const import (
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_APP_TOKEN,
    DOMAIN,
)
from .coordinator import GroceryAppConfigEntry, GroceryAppCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.TODO]

__all__ = ["DOMAIN", "async_setup_entry", "async_unload_entry"]


async def async_setup_entry(hass: HomeAssistant, entry: GroceryAppConfigEntry) -> bool:
    """Set up Grocery App from a config entry."""
    client = GroceryAppClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_ACCESS_CLIENT_ID],
        entry.data[CONF_ACCESS_CLIENT_SECRET],
        entry.data[CONF_APP_TOKEN],
    )
    coordinator = GroceryAppCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GroceryAppConfigEntry) -> bool:
    """Unload a Grocery App config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
