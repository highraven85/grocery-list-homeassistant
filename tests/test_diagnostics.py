"""Diagnostics tests."""

from __future__ import annotations

import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.grocery_app.diagnostics import async_get_config_entry_diagnostics

from .common import (
    TEST_ACCESS_CLIENT_ID,
    TEST_ACCESS_CLIENT_SECRET,
    TEST_APP_TOKEN,
    TEST_BASE_URL,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_diagnostics_redact_url_and_credentials(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Diagnostics keep list counts and remove the URL and credentials."""
    entry = await setup_integration(hass, aioclient_mock)

    result = await async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(result)

    assert TEST_BASE_URL not in dumped
    assert TEST_ACCESS_CLIENT_ID not in dumped
    assert TEST_ACCESS_CLIENT_SECRET not in dumped
    assert TEST_APP_TOKEN not in dumped
    assert result["shopping_list"]["item_count"] == 2
    assert result["shopping_list"]["open_count"] == 1
    assert result["entry"]["data"]["app_token"] == "**REDACTED**"
    assert result["entry"]["data"]["url"] == "**REDACTED**"
