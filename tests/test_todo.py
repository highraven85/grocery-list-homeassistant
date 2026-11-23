"""To-do entity tests."""

from __future__ import annotations

import json

import pytest
from homeassistant.components.todo.const import DATA_COMPONENT
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .common import (
    ITEMS_URL,
    LIST_URL,
    TEST_ACCESS_CLIENT_SECRET,
    TEST_APP_TOKEN,
    assert_secret_headers,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _calls(aioclient_mock: AiohttpClientMocker, method: str) -> list[tuple]:
    return [call for call in aioclient_mock.mock_calls if call[0].lower() == method]


async def test_list_exposes_items_and_open_count(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The entity id, name, and open-item count come from the API payload."""
    await setup_integration(hass, aioclient_mock)

    state = hass.states.get("todo.grocery_app")
    assert state is not None
    assert state.name == "Grocery App"
    assert state.state == "1"
    entity = hass.data[DATA_COMPONENT].get_entity("todo.grocery_app")
    assert entity is not None
    assert [
        (item.uid, item.summary, item.status, item.description)
        for item in entity.todo_items
    ] == [
        ("milk", "Milk", "needs_action", "Whole"),
        ("bread", "Bread", "completed", None),
    ]
    assert_secret_headers(
        aioclient_mock.mock_calls[0][3], aioclient_mock.mock_calls[0][1]
    )


async def test_add_complete_rename_and_remove(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """To-do actions call the matching API methods."""
    await setup_integration(hass, aioclient_mock)
    aioclient_mock.post(
        ITEMS_URL,
        json={"id": "eggs", "name": "Eggs", "status": "needs_action"},
    )
    aioclient_mock.patch(
        f"{ITEMS_URL}/milk",
        json={"id": "milk", "name": "Milk", "status": "completed"},
    )
    aioclient_mock.delete(f"{ITEMS_URL}/bread")
    aioclient_mock.delete(f"{ITEMS_URL}/milk")

    await hass.services.async_call(
        "todo",
        "add_item",
        {ATTR_ENTITY_ID: "todo.grocery_app", "item": "Eggs"},
        blocking=True,
    )
    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: "todo.grocery_app", "item": "Milk", "status": "completed"},
        blocking=True,
    )
    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: "todo.grocery_app", "item": "milk", "rename": "Oat milk"},
        blocking=True,
    )
    await hass.services.async_call(
        "todo",
        "remove_item",
        {ATTR_ENTITY_ID: "todo.grocery_app", "item": ["Bread", "milk"]},
        blocking=True,
    )

    post = _calls(aioclient_mock, "post")
    assert len(post) == 1
    assert_secret_headers(post[0][3], post[0][1])
    assert post[0][2] == {"name": "Eggs"}

    patches = _calls(aioclient_mock, "patch")
    assert [json.loads(json.dumps(call[2])) for call in patches] == [
        {"name": "Milk", "status": "completed"},
        {"name": "Oat milk", "status": "needs_action"},
    ]
    for call in patches:
        assert_secret_headers(call[3], call[1])
        assert str(call[1]) == f"{ITEMS_URL}/milk"

    deletes = _calls(aioclient_mock, "delete")
    assert [str(call[1]) for call in deletes] == [
        f"{ITEMS_URL}/bread",
        f"{ITEMS_URL}/milk",
    ]
    for call in deletes:
        assert_secret_headers(call[3], call[1])


async def test_add_failure_does_not_include_secrets(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed add raises a generic error and does not log the token."""
    await setup_integration(hass, aioclient_mock)
    aioclient_mock.post(ITEMS_URL, status=500, text=TEST_APP_TOKEN)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo",
            "add_item",
            {ATTR_ENTITY_ID: "todo.grocery_app", "item": "Eggs"},
            blocking=True,
        )

    assert TEST_APP_TOKEN not in caplog.text
    assert TEST_ACCESS_CLIENT_SECRET not in caplog.text


async def test_auth_failure_while_polling_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A later 401 marks the entity unavailable and starts reauthentication."""
    entry = await setup_integration(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(LIST_URL, status=401, text="denied")

    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("todo.grocery_app")
    assert state is not None
    assert state.state == "unavailable"
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == SOURCE_REAUTH for flow in flows)


async def test_setup_auth_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Invalid stored credentials fail setup and start reauthentication."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.grocery_app.const import DOMAIN

    from .common import config_data

    aioclient_mock.get(LIST_URL, status=403, text="denied")
    entry = MockConfigEntry(domain=DOMAIN, data=config_data(), unique_id=DOMAIN)
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == SOURCE_REAUTH for flow in flows)


async def test_unload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Unloading the entry removes the to-do entity."""
    entry = await setup_integration(hass, aioclient_mock)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.data[DATA_COMPONENT].get_entity("todo.grocery_app") is None
    state = hass.states.get("todo.grocery_app")
    assert state is not None
    assert state.state == "unavailable"
