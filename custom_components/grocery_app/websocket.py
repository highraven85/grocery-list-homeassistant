"""Websocket command used by the Grocery App Lovelace card."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .api import GroceryAppClient, GroceryAppError
from .calendar import dinners_by_day
from .const import DOMAIN, PHOTO_URL_PREFIX, WS_MEALS_MAX_DAYS


def loaded_client(hass: HomeAssistant) -> GroceryAppClient | None:
    """Return the client of the loaded Grocery App entry, if any."""
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        return entry.runtime_data.client
    return None


def photo_path(recipe_id: str) -> str:
    """Return the Home Assistant path that proxies a recipe photo."""
    return f"{PHOTO_URL_PREFIX}/{quote(recipe_id, safe='')}"


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the card's websocket commands."""
    websocket_api.async_register_command(hass, ws_dinners)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "grocery_app/dinners",
        vol.Required("start"): cv.date,
        vol.Required("end"): cv.date,
    }
)
@websocket_api.async_response
async def ws_dinners(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return planned dinners with recipe ids and proxied photo paths."""
    start, end = msg["start"], msg["end"]
    if end < start or (end - start).days >= WS_MEALS_MAX_DAYS:
        connection.send_error(msg["id"], "invalid_format", "Invalid date range")
        return
    client = loaded_client(hass)
    if client is None:
        connection.send_error(msg["id"], "not_loaded", "Grocery App is not loaded")
        return
    try:
        meals = await client.async_get_meals(start, end)
    except GroceryAppError:
        connection.send_error(
            msg["id"], "request_failed", "Grocery App dinners could not be loaded"
        )
        return
    connection.send_result(
        msg["id"],
        {
            "dinners": [
                {
                    "date": day.isoformat(),
                    "recipes": [
                        {
                            "id": recipe.id,
                            "name": recipe.name,
                            "photo": photo_path(recipe.id)
                            if client.has_photo(recipe.id)
                            else None,
                        }
                        for recipe in recipes
                    ],
                }
                for day, recipes in dinners_by_day(meals).items()
            ]
        },
    )
