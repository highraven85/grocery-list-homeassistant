"""Config flow for the Grocery App integration."""

from __future__ import annotations

import logging
from typing import Any, override

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    GroceryAppAuthError,
    GroceryAppClient,
    GroceryAppConnectionError,
    GroceryAppError,
    GroceryAppInvalidUrlError,
    normalize_base_url,
)
from .const import (
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_APP_TOKEN,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_SECRET_FIELDS = (
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_APP_TOKEN,
)


def _password_selector(autocomplete: str) -> TextSelector:
    """Return a password field selector."""
    config: TextSelectorConfig = {
        "type": TextSelectorType.PASSWORD,
        "autocomplete": autocomplete,
    }
    return TextSelector(config)


def _user_schema(
    *, include_url: bool, suggested_url: str | None = None
) -> probatio.Schema:
    """Build the config form. Secrets are password fields and have no default."""
    fields: dict[Any, Any] = {}
    if include_url:
        url_selector = TextSelector(
            {
                "type": TextSelectorType.URL,
                "autocomplete": "url",
            }
        )
        if suggested_url is None:
            fields[probatio.Required(CONF_URL)] = url_selector
        else:
            fields[probatio.Required(CONF_URL, default=suggested_url)] = url_selector
    fields[probatio.Required(CONF_ACCESS_CLIENT_ID)] = _password_selector("off")
    fields[probatio.Required(CONF_ACCESS_CLIENT_SECRET)] = _password_selector(
        "current-password"
    )
    fields[probatio.Required(CONF_APP_TOKEN)] = _password_selector("current-password")
    return probatio.Schema(fields)


class GroceryAppConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grocery App."""

    VERSION = 1

    async def _async_validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Check the URL and credentials. Return form errors, or an empty dict."""
        try:
            base_url = normalize_base_url(str(user_input[CONF_URL]))
        except GroceryAppInvalidUrlError:
            return {CONF_URL: "invalid_url"}

        secrets = {key: str(user_input[key]).strip() for key in _SECRET_FIELDS}
        if any(not value for value in secrets.values()):
            return {"base": "invalid_auth"}

        client = GroceryAppClient(
            async_get_clientsession(self.hass),
            base_url,
            secrets[CONF_ACCESS_CLIENT_ID],
            secrets[CONF_ACCESS_CLIENT_SECRET],
            secrets[CONF_APP_TOKEN],
        )
        try:
            await client.async_get_list()
        except GroceryAppAuthError:
            _LOGGER.error("Grocery App rejected the credentials during setup")
            return {"base": "invalid_auth"}
        except GroceryAppConnectionError:
            _LOGGER.error("Grocery App could not be reached during setup")
            return {"base": "cannot_connect"}
        except GroceryAppError:
            _LOGGER.error("Grocery App returned an unexpected response during setup")
            return {"base": "invalid_response"}
        except Exception:
            _LOGGER.exception("Unexpected Grocery App setup error")
            return {"base": "unknown"}

        user_input[CONF_URL] = base_url
        user_input.update(secrets)
        return {}

    def _entry_data(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Return the normalized values stored in the config entry."""
        return {
            CONF_URL: user_input[CONF_URL],
            CONF_ACCESS_CLIENT_ID: user_input[CONF_ACCESS_CLIENT_ID],
            CONF_ACCESS_CLIENT_SECRET: user_input[CONF_ACCESS_CLIENT_SECRET],
            CONF_APP_TOKEN: user_input[CONF_APP_TOKEN],
        }

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data=self._entry_data(user_input),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(include_url=True),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after a credential failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials and keep the stored base URL."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            combined = {**entry.data, **user_input}
            errors = await self._async_validate(combined)
            if CONF_URL in errors:
                errors = {"base": "invalid_url"}
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=self._entry_data(combined),
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_user_schema(include_url=False),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace the base URL and credentials."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data=self._entry_data(user_input),
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(
                include_url=True,
                suggested_url=str(entry.data[CONF_URL]),
            ),
            errors=errors,
        )
