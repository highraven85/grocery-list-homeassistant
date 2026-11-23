"""Tests for the grocery app HTTP client."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from aiohttp import ClientError

from custom_components.grocery_app.api import (
    HEADER_ACCESS_CLIENT_ID,
    HEADER_ACCESS_CLIENT_SECRET,
    HEADER_AUTHORIZATION,
    GroceryAppApiError,
    GroceryAppAuthError,
    GroceryAppClient,
    GroceryAppConnectionError,
    GroceryAppInvalidUrlError,
    GroceryAppResponseError,
    normalize_base_url,
)

ACCESS_CLIENT_ID = "client-id"
ACCESS_CLIENT_SECRET = "client-secret"
APP_TOKEN = "app-token"


class _Response:
    """Async context manager that stands in for an aiohttp response."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _Session:
    """Record requests and return scripted responses without opening a socket."""

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        self.calls.append((method, url, kwargs))
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        status, payload = outcome
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload).encode()
        elif isinstance(payload, str):
            body = payload.encode()
        else:
            body = payload
        return _Response(status, body)


def _client(
    session: _Session, base_url: str = "https://example.com"
) -> GroceryAppClient:
    return GroceryAppClient(
        session,  # type: ignore[arg-type]
        base_url,
        ACCESS_CLIENT_ID,
        ACCESS_CLIENT_SECRET,
        APP_TOKEN,
        retry_delays=(0, 0),
        timeout=1,
    )


def _assert_headers(call: tuple[str, str, dict[str, Any]]) -> None:
    headers = call[2]["headers"]
    assert headers[HEADER_AUTHORIZATION] == f"Bearer {APP_TOKEN}"
    assert headers[HEADER_ACCESS_CLIENT_ID] == ACCESS_CLIENT_ID
    assert headers[HEADER_ACCESS_CLIENT_SECRET] == ACCESS_CLIENT_SECRET
    assert "?" not in call[1]
    assert APP_TOKEN not in call[1]
    assert ACCESS_CLIENT_SECRET not in call[1]
    assert call[2]["allow_redirects"] is False


def test_normalize_base_url_strips_trailing_slash_and_keeps_path() -> None:
    """A path prefix is preserved and a trailing slash is removed."""
    assert (
        normalize_base_url("https://example.com/grocery/")
        == "https://example.com/grocery"
    )
    assert normalize_base_url(" https://example.com ") == "https://example.com"


@pytest.mark.parametrize(
    "value",
    [
        "example.com",
        "ftp://example.com",
        "https://user:pw@example.com",
        "https://example.com/grocery?a=b",
        "https://example.com/grocery#part",
        "",
        "   ",
    ],
)
def test_normalize_base_url_rejects_unsafe_values(value: str) -> None:
    """Userinfo, queries, fragments, and missing schemes are rejected."""
    with pytest.raises(GroceryAppInvalidUrlError):
        normalize_base_url(value)


async def test_get_list_sends_credential_headers_and_not_a_query() -> None:
    """Credentials travel in headers, and the URL has no query string."""
    session = _Session(
        [
            (
                200,
                {
                    "name": "Shopping list",
                    "items": [
                        {
                            "id": "1",
                            "name": "Milk",
                            "status": "needs_action",
                            "description": "Cold",
                        },
                        {"id": 2, "name": "Eggs", "status": "completed"},
                        {"name": "Skipped"},
                    ],
                },
            )
        ]
    )
    shopping_list = await _client(
        session, "https://example.com/grocery/"
    ).async_get_list()

    assert shopping_list.name == "Shopping list"
    assert [item.name for item in shopping_list.items] == ["Milk", "Eggs"]
    assert shopping_list.items[0].description == "Cold"
    assert shopping_list.items[1].id == "2"
    assert session.calls[0][0] == "GET"
    assert session.calls[0][1] == "https://example.com/grocery/api/ha/todo"
    _assert_headers(session.calls[0])


async def test_mutations_use_json_bodies_and_encoded_ids() -> None:
    """Add, update, and delete use the documented paths and bodies."""
    session = _Session(
        [
            (201, {"id": "3", "name": "Milk & eggs", "status": "needs_action"}),
            (200, {"id": "a/b c", "name": "Rice", "status": "completed"}),
            (204, ""),
        ]
    )
    client = _client(session)
    created = await client.async_add_item("  Milk & eggs  ")
    await client.async_update_item("a/b c", name="Rice", status="completed")
    await client.async_delete_item("a/b c")

    assert created["name"] == "Milk & eggs"
    assert session.calls[0][1] == "https://example.com/api/ha/todo/items"
    assert session.calls[0][2]["json"] == {"name": "Milk & eggs"}
    assert session.calls[1][0] == "PATCH"
    assert session.calls[1][1] == "https://example.com/api/ha/todo/items/a%2Fb%20c"
    assert session.calls[1][2]["json"] == {"name": "Rice", "status": "completed"}
    assert session.calls[2][0] == "DELETE"
    assert session.calls[2][1] == "https://example.com/api/ha/todo/items/a%2Fb%20c"
    for call in session.calls:
        _assert_headers(call)


async def test_auth_failure_is_not_retried_or_logged_with_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 403 is terminal, and the response body is not written to the log."""
    session = _Session([(403, APP_TOKEN)])
    caplog.set_level(logging.DEBUG, logger="custom_components.grocery_app")

    with pytest.raises(GroceryAppAuthError):
        await _client(session).async_get_list()

    assert len(session.calls) == 1
    messages = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("custom_components.grocery_app")
    )
    assert "HTTP 403" in messages
    assert APP_TOKEN not in messages
    assert ACCESS_CLIENT_SECRET not in messages


async def test_server_errors_are_retried() -> None:
    """503 responses are retried, and a later success is returned."""
    session = _Session(
        [
            (503, "busy"),
            (503, "busy"),
            (200, {"name": "Shopping list", "items": []}),
        ]
    )
    shopping_list = await _client(session).async_get_list()

    assert shopping_list.items == ()
    assert len(session.calls) == 3


async def test_connection_errors_are_retried() -> None:
    """Connection failures are retried and then reported without the URL."""
    session = _Session([ClientError(), TimeoutError(), ClientError()])

    with pytest.raises(GroceryAppConnectionError):
        await _client(session).async_get_list()

    assert len(session.calls) == 3


async def test_invalid_json_and_http_errors() -> None:
    """Malformed payloads and ordinary HTTP errors are not retried."""
    invalid = _Session([(200, "not-json")])
    with pytest.raises(GroceryAppResponseError):
        await _client(invalid).async_get_list()
    assert len(invalid.calls) == 1

    missing = _Session([(404, "missing")])
    with pytest.raises(GroceryAppApiError):
        await _client(missing).async_get_list()
    assert len(missing.calls) == 1
