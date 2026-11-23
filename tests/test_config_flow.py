"""Config flow tests."""

from __future__ import annotations

import logging

import pytest
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntryState,
)
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.grocery_app.const import (
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_APP_TOKEN,
    DOMAIN,
)

from .common import (
    LIST_URL,
    TEST_ACCESS_CLIENT_ID,
    TEST_ACCESS_CLIENT_SECRET,
    TEST_APP_TOKEN,
    TEST_BASE_URL,
    assert_secret_headers,
    config_data,
    list_payload,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _selector_types(schema) -> dict[str, str]:
    return {
        key.schema: selector.config["type"] for key, selector in schema.schema.items()
    }


async def test_user_form_uses_password_fields(
    hass: HomeAssistant,
) -> None:
    """The credential fields are password inputs and the URL has no default host."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    types = _selector_types(result["data_schema"])
    assert types == {
        CONF_URL: "url",
        CONF_ACCESS_CLIENT_ID: "password",
        CONF_ACCESS_CLIENT_SECRET: "password",
        CONF_APP_TOKEN: "password",
    }


@pytest.mark.parametrize(
    "url",
    [
        "example.com",
        "ftp://example.com",
        "https://user:pw@example.com",
        "https://example.com/grocery?a=b",
    ],
)
async def test_invalid_url_does_not_call_the_api(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    url: str,
) -> None:
    """Unsafe base URLs are rejected before a request is made."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        config_data(**{CONF_URL: url}),
    )

    assert result["type"] == "form"
    assert result["errors"]["url"] == "invalid_url"
    assert aioclient_mock.call_count == 0


async def test_invalid_auth_is_shown_and_secrets_are_not_logged(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 403 becomes invalid_auth and the log omits the credentials."""
    aioclient_mock.get(LIST_URL, status=403, text=TEST_APP_TOKEN)
    caplog.set_level(logging.DEBUG)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        config_data(),
    )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_auth"
    assert TEST_APP_TOKEN not in caplog.text
    assert TEST_ACCESS_CLIENT_SECRET not in caplog.text
    assert TEST_ACCESS_CLIENT_ID not in caplog.text
    assert_secret_headers(
        aioclient_mock.mock_calls[0][3], aioclient_mock.mock_calls[0][1]
    )


async def test_cannot_connect(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Connection failures stay on the form."""
    aioclient_mock.get(LIST_URL, exc=TimeoutError())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        config_data(),
    )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"


async def test_successful_setup_creates_the_todo_entity(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A valid account creates the Grocery App to-do list."""
    aioclient_mock.get(LIST_URL, json=list_payload())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        config_data(**{CONF_URL: "https://example.com/"}),
    )
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["title"] == "Grocery App"
    assert result["data"][CONF_URL] == TEST_BASE_URL
    assert result["data"][CONF_APP_TOKEN] == TEST_APP_TOKEN
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get("todo.grocery_app")
    assert state is not None
    assert state.name == "Grocery App"
    assert state.state == "1"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


async def test_reauth_updates_credentials(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Reauthentication replaces the credentials and keeps the base URL."""
    aioclient_mock.get(LIST_URL, json=list_payload())
    start = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    created = await hass.config_entries.flow.async_configure(
        start["flow_id"], config_data()
    )
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(created["result"].entry_id)
    assert entry is not None

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=dict(entry.data),
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"
    assert CONF_URL not in _selector_types(result["data_schema"])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ACCESS_CLIENT_ID: "client-id-2",
            CONF_ACCESS_CLIENT_SECRET: "client-secret-2",
            CONF_APP_TOKEN: "app-token-2",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_URL] == TEST_BASE_URL
    assert entry.data[CONF_APP_TOKEN] == "app-token-2"
    assert entry.data[CONF_ACCESS_CLIENT_SECRET] == "client-secret-2"


async def test_reconfigure_updates_the_base_url(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Reconfigure stores a new base URL and new credentials."""
    aioclient_mock.get(LIST_URL, json=list_payload())
    aioclient_mock.get("https://example.org/api/ha/todo", json=list_payload())
    start = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    created = await hass.config_entries.flow.async_configure(
        start["flow_id"], config_data()
    )
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(created["result"].entry_id)
    assert entry is not None

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        config_data(
            **{
                CONF_URL: "https://example.org/",
                CONF_ACCESS_CLIENT_ID: "client-id-2",
                CONF_ACCESS_CLIENT_SECRET: "client-secret-2",
                CONF_APP_TOKEN: "app-token-2",
            }
        ),
    )
    await hass.async_block_till_done()

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_URL] == "https://example.org"
    assert entry.data[CONF_APP_TOKEN] == "app-token-2"
    assert hass.states.get("todo.grocery_app") is not None
