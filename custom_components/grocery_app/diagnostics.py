"""Diagnostics for the Grocery App integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from .api import (
    HEADER_ACCESS_CLIENT_ID,
    HEADER_ACCESS_CLIENT_SECRET,
    HEADER_AUTHORIZATION,
)
from .const import CONF_ACCESS_CLIENT_ID, CONF_ACCESS_CLIENT_SECRET, CONF_APP_TOKEN
from .coordinator import GroceryAppConfigEntry

TO_REDACT = {
    CONF_URL,
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_APP_TOKEN,
    HEADER_AUTHORIZATION,
    HEADER_ACCESS_CLIENT_ID,
    HEADER_ACCESS_CLIENT_SECRET,
    "authorization",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: GroceryAppConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics with the base URL and credentials removed."""
    coordinator = entry.runtime_data
    data = coordinator.data
    open_count = None
    item_count = None
    if data is not None:
        item_count = len(data.items)
        open_count = sum(item.status == "needs_action" for item in data.items)
    return async_redact_data(
        {
            "entry": entry.as_dict(),
            "shopping_list": {
                "item_count": item_count,
                "open_count": open_count,
                "last_update_success": coordinator.last_update_success,
            },
        },
        TO_REDACT,
    )
