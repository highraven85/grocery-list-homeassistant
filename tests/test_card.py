"""Card support: departments, dinners websocket command, photo proxy, card script.

Meal and photo data here is example data.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.grocery_app.api import GroceryAppClient

from .common import (
    TEST_ACCESS_CLIENT_SECRET,
    TEST_APP_TOKEN,
    TEST_BASE_URL,
    list_payload,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

PHOTO_URL = f"{TEST_BASE_URL}/api/ha/media/r/taco.jpg"
JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 400  # ~100 KB, spans buffers


def _meals() -> list[dict[str, Any]]:
    return [
        {
            "date": "2026-11-23",
            "meal": "dinner",
            "recipes": [
                {"id": "r1", "name": "Chicken Tacos", "photo_url": PHOTO_URL},
                {"id": "r2", "name": "Mexican Rice", "photo_url": None},
            ],
        },
        {
            "date": "2026-11-23",
            "meal": "lunch",
            "recipes": [{"id": "r3", "name": "Soup", "photo_url": None}],
        },
        {
            "date": "2026-11-24",
            "meal": "dinner",
            "recipes": [
                {
                    "id": "r9",
                    "name": "Evil",
                    "photo_url": "https://elsewhere.example/api/ha/media/r/x.jpg",
                }
            ],
        },
    ]


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, **kw: Any):
    assert await async_setup_component(hass, "http", {})
    return await setup_integration(hass, aioclient_mock, **kw)


async def test_departments_are_exposed_as_unrecorded_attributes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Departments from the app become todo attributes for the card."""
    payload = list_payload(
        [
            {
                "id": "milk",
                "name": "Milk",
                "status": "needs_action",
                "department": "Dairy & Eggs",
            },
            {"id": "kale", "name": "Kale", "status": "needs_action"},
        ]
    )
    payload["departments"] = ["Produce", "Dairy & Eggs", "Produce", 5]
    await _setup(hass, aioclient_mock, payload=payload, meals=[])
    state = hass.states.get("todo.grocery_app")
    assert state.attributes["department_order"] == ["Produce", "Dairy & Eggs"]
    assert state.attributes["item_departments"] == {"milk": "Dairy & Eggs"}
    entity = hass.data["todo"].get_entity("todo.grocery_app")
    assert "item_departments" in entity._unrecorded_attributes


async def test_no_department_attributes_without_departments(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Today's app payload (no departments) adds no attributes."""
    await _setup(hass, aioclient_mock, meals=[])
    state = hass.states.get("todo.grocery_app")
    assert "item_departments" not in state.attributes


async def test_dinners_websocket(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_ws_client
) -> None:
    """The websocket command returns dinners with proxied photo paths only."""
    await _setup(hass, aioclient_mock, meals=_meals())
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "grocery_app/dinners", "start": "2026-11-23", "end": "2026-11-29"}
    )
    msg = await client.receive_json()
    assert msg["success"], msg
    assert msg["result"]["dinners"] == [
        {
            "date": "2026-11-23",
            "recipes": [
                {
                    "id": "r1",
                    "name": "Chicken Tacos",
                    "photo": "/api/grocery_app/recipe_photo/r1",
                },
                {"id": "r2", "name": "Mexican Rice", "photo": None},
            ],
        },
        {
            "date": "2026-11-24",
            "recipes": [{"id": "r9", "name": "Evil", "photo": None}],
        },
    ]
    assert TEST_APP_TOKEN not in str(msg)
    assert TEST_BASE_URL not in str(msg)

    await client.send_json_auto_id(
        {"type": "grocery_app/dinners", "start": "2026-11-29", "end": "2026-11-23"}
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"


async def test_dinners_websocket_api_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_ws_client
) -> None:
    """API failures return a generic error without secrets."""
    await _setup(hass, aioclient_mock, meals_status=404)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "grocery_app/dinners", "start": "2026-11-23", "end": "2026-11-29"}
    )
    msg = await client.receive_json()
    assert msg["error"]["code"] == "request_failed"
    assert TEST_APP_TOKEN not in str(msg)


async def test_photo_proxy(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_client
) -> None:
    """Known photos are proxied with app credentials; others are 404."""
    await _setup(hass, aioclient_mock, meals=_meals())
    aioclient_mock.get(PHOTO_URL, content=JPEG, headers={"Content-Type": "image/jpeg"})
    entry_client: GroceryAppClient = hass.config_entries.async_entries("grocery_app")[
        0
    ].runtime_data.client
    await entry_client.async_get_meals(date(2026, 11, 23), date(2026, 11, 29))

    http = await hass_client()
    resp = await http.get("/api/grocery_app/recipe_photo/r1")
    assert resp.status == 200
    assert resp.content_type == "image/jpeg"
    assert await resp.read() == JPEG
    photo_call = [c for c in aioclient_mock.mock_calls if str(c[1]) == PHOTO_URL][-1]
    assert photo_call[3]["Authorization"] == f"Bearer {TEST_APP_TOKEN}"
    assert photo_call[3]["CF-Access-Client-Secret"] == TEST_ACCESS_CLIENT_SECRET

    for unknown in ("r2", "r9", "nope"):
        resp = await http.get(f"/api/grocery_app/recipe_photo/{unknown}")
        assert resp.status == 404


async def test_photo_proxy_requires_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_client_no_auth
) -> None:
    """The photo proxy is not public."""
    await _setup(hass, aioclient_mock, meals=_meals())
    http = await hass_client_no_auth()
    resp = await http.get("/api/grocery_app/recipe_photo/r1")
    assert resp.status == 401


async def test_photo_rejects_non_images(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_client
) -> None:
    """A non-image response is not passed through."""
    await _setup(hass, aioclient_mock, meals=_meals())
    aioclient_mock.get(PHOTO_URL, text="<html>", headers={"Content-Type": "text/html"})
    http = await hass_client()
    resp = await http.get("/api/grocery_app/recipe_photo/r1")
    assert resp.status == 502


async def test_card_script_is_served(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_client
) -> None:
    """The bundled card is served from the integration's static path."""
    await _setup(hass, aioclient_mock, meals=[])
    http = await hass_client()
    resp = await http.get("/grocery_app_static/grocery-app-card.js")
    assert resp.status == 200
    body = await resp.text()
    assert 'customElements.define("grocery-app-card"' in body
    assert "http://" not in body.replace("http://www.w3.org", "")
