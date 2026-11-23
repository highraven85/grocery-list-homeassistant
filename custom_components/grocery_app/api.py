"""HTTP client for the grocery app shopping-list API.

Credentials are sent only as headers. They are never added to the URL.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout
from yarl import URL

from .const import API_STATUSES

_LOGGER = logging.getLogger(__name__)

HEADER_ACCEPT = "Accept"
HEADER_AUTHORIZATION = "Authorization"
HEADER_ACCESS_CLIENT_ID = "CF-Access-Client-Id"
HEADER_ACCESS_CLIENT_SECRET = "CF-Access-Client-Secret"
_BEARER = "Bearer"

_AUTH_STATUSES = frozenset({401, 403})
_RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_DEFAULT_RETRY_DELAYS = (0.5, 1.0, 2.0)
_DEFAULT_TIMEOUT = 20.0


class GroceryAppError(Exception):
    """Base error for the grocery app client.

    Messages stay free of credentials, response bodies, and request URLs.
    """


class GroceryAppAuthError(GroceryAppError):
    """The grocery app or Cloudflare Access rejected the credentials."""

    def __init__(self, status: int) -> None:
        """Store the HTTP status without a response body."""
        self.status = status
        super().__init__(f"Authentication failed with HTTP {status}")


class GroceryAppConnectionError(GroceryAppError):
    """The grocery app could not be reached."""

    def __init__(self) -> None:
        """Use a fixed message that does not include the host."""
        super().__init__("Could not connect to the grocery app")


class GroceryAppApiError(GroceryAppError):
    """The grocery app returned an error response."""

    def __init__(self, status: int, method: str, path: str) -> None:
        """Store the status and relative path, never the base URL."""
        self.status = status
        self.method = method
        self.path = path
        super().__init__(f"{method} {path} failed with HTTP {status}")


class GroceryAppResponseError(GroceryAppError):
    """The grocery app returned a response this client cannot use."""

    def __init__(self) -> None:
        """Use a fixed message that does not include the payload."""
        super().__init__("The grocery app returned an unexpected response")


class GroceryAppInvalidUrlError(GroceryAppError):
    """The configured base URL cannot be used safely."""

    def __init__(self) -> None:
        """Use a fixed message that does not echo the URL."""
        super().__init__("Invalid grocery app base URL")


@dataclass(frozen=True, slots=True)
class GroceryItem:
    """One shopping-list item from the grocery app."""

    id: str
    name: str
    status: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class GroceryList:
    """Shopping list returned by the grocery app."""

    name: str
    items: tuple[GroceryItem, ...]


def normalize_base_url(value: str) -> str:
    """Return a base URL that is safe to join with the API path.

    Userinfo, query strings, and fragments are rejected so a credential cannot
    be smuggled into the request URL.
    """
    try:
        parsed = URL(value.strip())
    except ValueError as err:
        raise GroceryAppInvalidUrlError from err
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise GroceryAppInvalidUrlError
    if (
        parsed.user is not None
        or parsed.password is not None
        or parsed.query_string
        or parsed.fragment
    ):
        raise GroceryAppInvalidUrlError
    path = parsed.path.rstrip("/")
    normalized = parsed.with_path(path or "/").with_query(None).with_fragment(None)
    return str(normalized).rstrip("/")


def _parse_item(raw: Any, index: int) -> GroceryItem | None:
    """Convert one API item, or skip it when the shape is unusable."""
    if not isinstance(raw, dict):
        _LOGGER.warning(
            "Skipping shopping list item %s because it is not an object", index
        )
        return None

    item_id = raw.get("id")
    if isinstance(item_id, int) and not isinstance(item_id, bool):
        item_id = str(item_id)
    name = raw.get("name")
    status = raw.get("status")
    if not isinstance(item_id, str) or not item_id.strip():
        _LOGGER.warning("Skipping shopping list item %s because it has no id", index)
        return None
    if not isinstance(name, str) or not name.strip():
        _LOGGER.warning("Skipping shopping list item %s because it has no name", index)
        return None
    if status not in API_STATUSES:
        _LOGGER.warning(
            "Skipping shopping list item %s because its status is not recognized",
            index,
        )
        return None

    description = raw.get("description")
    if not isinstance(description, str):
        description = None
    return GroceryItem(
        id=item_id.strip(),
        name=name.strip(),
        status=status,
        description=description,
    )


class GroceryAppClient:
    """Call the grocery app Home Assistant API."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        access_client_id: str,
        access_client_secret: str,
        app_token: str,
        *,
        retry_delays: tuple[float, ...] = _DEFAULT_RETRY_DELAYS,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Store the session and credentials.

        ``retry_delays`` is the wait before each retry. The number of attempts
        is one more than the number of delays.
        """
        self._session = session
        self._base_url = normalize_base_url(base_url)
        self._access_client_id = access_client_id
        self._access_client_secret = access_client_secret
        self._app_token = app_token
        self._retry_delays = retry_delays
        self._timeout = timeout

    def __repr__(self) -> str:
        """Return a representation that omits the URL and credentials."""
        return "GroceryAppClient(<redacted>)"

    def _headers(self) -> dict[str, str]:
        """Build request headers. Callers must not log the result."""
        return {
            HEADER_ACCEPT: "application/json",
            HEADER_AUTHORIZATION: f"{_BEARER} {self._app_token}",
            HEADER_ACCESS_CLIENT_ID: self._access_client_id,
            HEADER_ACCESS_CLIENT_SECRET: self._access_client_secret,
        }

    def _build_url(self, *parts: str) -> str:
        """Join the base URL with one encoded segment per part and no query."""
        url = URL(self._base_url)
        for part in parts:
            if not part or part in {".", ".."} or any(ord(char) < 32 for char in part):
                raise GroceryAppInvalidUrlError
            url = url.joinpath(quote(part, safe=""), encoded=True)
        if url.user is not None or url.query_string or url.fragment:
            raise GroceryAppInvalidUrlError
        return str(url)

    async def _pause(self, attempt: int) -> None:
        """Wait before the next attempt. ``attempt`` is 1-based."""
        delay = self._retry_delays[attempt - 1]
        if delay:
            await asyncio.sleep(delay)

    async def _request_json(
        self,
        method: str,
        *parts: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        """Perform one API request and return decoded JSON, or None."""
        url = self._build_url(*parts)
        path = "/" + "/".join(parts)
        attempts = len(self._retry_delays) + 1

        for attempt in range(1, attempts + 1):
            try:
                request_kwargs: dict[str, Any] = {
                    "headers": self._headers(),
                    "timeout": ClientTimeout(total=self._timeout),
                    "allow_redirects": False,
                }
                if json_body is not None:
                    request_kwargs["json"] = dict(json_body)
                async with self._session.request(
                    method, url, **request_kwargs
                ) as response:
                    body = await response.read()
                    status = response.status
            except (ClientError, TimeoutError) as err:
                if attempt >= attempts:
                    _LOGGER.error(
                        "Grocery App could not connect for %s %s after %s attempts",
                        method,
                        path,
                        attempt,
                    )
                    raise GroceryAppConnectionError from err
                _LOGGER.warning(
                    "Grocery App connection problem for %s %s (attempt %s of %s)",
                    method,
                    path,
                    attempt,
                    attempts,
                )
                await self._pause(attempt)
                continue

            if status in _AUTH_STATUSES or 300 <= status < 400:
                _LOGGER.error(
                    "Grocery App authentication failed for %s %s with HTTP %s",
                    method,
                    path,
                    status,
                )
                raise GroceryAppAuthError(status)

            if status in _RETRY_STATUSES and attempt < attempts:
                _LOGGER.warning(
                    "Grocery App received HTTP %s for %s %s (attempt %s of %s)",
                    status,
                    method,
                    path,
                    attempt,
                    attempts,
                )
                await self._pause(attempt)
                continue

            if status >= 400:
                _LOGGER.error(
                    "Grocery App request failed for %s %s with HTTP %s",
                    method,
                    path,
                    status,
                )
                raise GroceryAppApiError(status, method, path)

            if not body:
                return None
            try:
                return json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as err:
                _LOGGER.error(
                    "Grocery App returned invalid JSON for %s %s",
                    method,
                    path,
                )
                raise GroceryAppResponseError from err

        raise GroceryAppConnectionError

    async def async_get_list(self) -> GroceryList:
        """Fetch the current shopping list."""
        payload = await self._request_json("GET", "api", "ha", "todo")
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            _LOGGER.error(
                "Grocery App shopping list response was not in the expected shape"
            )
            raise GroceryAppResponseError

        raw_name = payload.get("name")
        list_name = (
            raw_name.strip()
            if isinstance(raw_name, str) and raw_name.strip()
            else "Shopping list"
        )
        items = tuple(
            item
            for index, raw in enumerate(payload["items"])
            if (item := _parse_item(raw, index)) is not None
        )
        return GroceryList(name=list_name, items=items)

    async def async_add_item(self, name: str) -> Any:
        """Add an item and return the response payload, when one was sent."""
        cleaned = name.strip()
        if not cleaned:
            raise GroceryAppApiError(400, "POST", "/api/ha/todo/items")
        return await self._request_json(
            "POST",
            "api",
            "ha",
            "todo",
            "items",
            json_body={"name": cleaned},
        )

    async def async_update_item(
        self,
        item_id: str,
        *,
        name: str | None = None,
        status: str | None = None,
    ) -> Any:
        """Rename an item, change its status, or both."""
        if not item_id.strip():
            raise GroceryAppApiError(400, "PATCH", "/api/ha/todo/items")
        body: dict[str, str] = {}
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise GroceryAppApiError(400, "PATCH", "/api/ha/todo/items")
            body["name"] = cleaned
        if status is not None:
            if status not in API_STATUSES:
                raise GroceryAppApiError(400, "PATCH", "/api/ha/todo/items")
            body["status"] = status
        if not body:
            raise GroceryAppApiError(400, "PATCH", "/api/ha/todo/items")
        return await self._request_json(
            "PATCH",
            "api",
            "ha",
            "todo",
            "items",
            item_id,
            json_body=body,
        )

    async def async_delete_item(self, item_id: str) -> None:
        """Remove one item."""
        if not item_id.strip():
            raise GroceryAppApiError(400, "DELETE", "/api/ha/todo/items")
        await self._request_json("DELETE", "api", "ha", "todo", "items", item_id)
