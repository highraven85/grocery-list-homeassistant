"""Shared fixtures for integration tests.

The credential strings below are placeholders used to assert request headers.
They are not real credentials.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.grocery_app.api import (
    HEADER_ACCESS_CLIENT_ID,
    HEADER_ACCESS_CLIENT_SECRET,
    HEADER_AUTHORIZATION,
)
from custom_components.grocery_app.const import (
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_APP_TOKEN,
    DEFAULT_NAME,
    DOMAIN,
)

TEST_BASE_URL = "https://example.com"
TEST_ACCESS_CLIENT_ID = "client-id"
TEST_ACCESS_CLIENT_SECRET = "client-secret"
TEST_APP_TOKEN = "app-token"
LIST_URL = f"{TEST_BASE_URL}/api/ha/todo"
ITEMS_URL = f"{TEST_BASE_URL}/api/ha/todo/items"
MEALS_URL = f"{TEST_BASE_URL}/api/ha/meals"


def config_data(**overrides: Any) -> dict[str, Any]:
    """Return config-flow input with placeholder credentials."""
    data: dict[str, Any] = {
        CONF_URL: TEST_BASE_URL,
        CONF_ACCESS_CLIENT_ID: TEST_ACCESS_CLIENT_ID,
        CONF_ACCESS_CLIENT_SECRET: TEST_ACCESS_CLIENT_SECRET,
        CONF_APP_TOKEN: TEST_APP_TOKEN,
    }
    data.update(overrides)
    return data


def list_payload(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return a shopping-list response."""
    if items is None:
        items = [
            {
                "id": "milk",
                "name": "Milk",
                "status": "needs_action",
                "description": "Whole",
            },
            {
                "id": "bread",
                "name": "Bread",
                "status": "completed",
            },
        ]
    return {"name": "Shopping list", "items": items}


def assert_secret_headers(headers: Any, url: Any) -> None:
    """Assert credentials are headers and are absent from the URL."""
    assert headers[HEADER_AUTHORIZATION] == f"Bearer {TEST_APP_TOKEN}"
    assert headers[HEADER_ACCESS_CLIENT_ID] == TEST_ACCESS_CLIENT_ID
    assert headers[HEADER_ACCESS_CLIENT_SECRET] == TEST_ACCESS_CLIENT_SECRET
    assert url.query_string == ""
    url_text = str(url)
    assert TEST_APP_TOKEN not in url_text
    assert TEST_ACCESS_CLIENT_SECRET not in url_text
    assert TEST_ACCESS_CLIENT_ID not in url_text


async def setup_integration(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    payload: dict[str, Any] | None = None,
    meals: list[dict[str, Any]] | None = None,
    meals_status: int | None = None,
) -> MockConfigEntry:
    """Create a loaded Grocery App config entry against the mocked API.

    ``meals`` or ``meals_status`` mocks ``GET /api/ha/meals`` for any range.
    """
    if meals is not None or meals_status is not None:
        aioclient_mock.get(
            MEALS_URL,
            json=meals if meals is not None else {"error": "x"},
            status=meals_status or 200,
        )
    aioclient_mock.get(
        LIST_URL, json=payload if payload is not None else list_payload()
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data(),
        unique_id=DOMAIN,
        title=DEFAULT_NAME,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry
