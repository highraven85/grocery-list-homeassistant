"""The Grocery App integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import GroceryAppClient
from .const import (
    CARD_FILENAME,
    CARD_URL_BASE,
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_APP_TOKEN,
    DOMAIN,
)
from .coordinator import GroceryAppConfigEntry, GroceryAppCoordinator
from .views import GroceryAppRecipePhotoView
from .websocket import async_register_websocket

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.TODO]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

FRONTEND_DIR = Path(__file__).parent / "frontend"

__all__ = ["DOMAIN", "async_setup", "async_setup_entry", "async_unload_entry"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> None | bool:
    """Register the card's websocket command, photo proxy, and card script."""
    async_register_websocket(hass)
    if hass.http is None:
        return True
    hass.http.register_view(GroceryAppRecipePhotoView())
    await _async_register_card(hass)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled card and load it on every dashboard."""
    from homeassistant.components.frontend import (  # noqa: PLC0415
        DATA_EXTRA_MODULE_URL,
        add_extra_js_url,
    )
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_BASE, str(FRONTEND_DIR), cache_headers=False)]
    )
    if DATA_EXTRA_MODULE_URL not in hass.data:
        _LOGGER.warning(
            "Grocery App card was not added automatically because the frontend "
            "is not loaded; add %s/%s as a dashboard resource",
            CARD_URL_BASE,
            CARD_FILENAME,
        )
        return
    integration = await async_get_integration(hass, DOMAIN)
    version = integration.version or "0"
    add_extra_js_url(hass, f"{CARD_URL_BASE}/{CARD_FILENAME}?v={version}")


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
