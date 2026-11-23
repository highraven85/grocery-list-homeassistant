"""Data update coordinator for the Grocery App shopping list."""

from __future__ import annotations

import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GroceryAppAuthError, GroceryAppClient, GroceryAppError, GroceryList
from .const import DEFAULT_NAME, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type GroceryAppConfigEntry = ConfigEntry[GroceryAppCoordinator]


class GroceryAppCoordinator(DataUpdateCoordinator[GroceryList]):
    """Poll the grocery app shopping list."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GroceryAppConfigEntry,
        client: GroceryAppClient,
    ) -> None:
        """Create a coordinator bound to one config entry."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DEFAULT_NAME,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    @override
    async def _async_update_data(self) -> GroceryList:
        """Fetch the shopping list, or raise an error Home Assistant can show."""
        try:
            return await self.client.async_get_list()
        except GroceryAppAuthError as err:
            _LOGGER.error(
                "Grocery App authentication failed while refreshing the shopping list"
            )
            raise ConfigEntryAuthFailed("Grocery App authentication failed") from err
        except GroceryAppError as err:
            _LOGGER.error("Grocery App shopping list could not be refreshed")
            raise UpdateFailed(
                "Grocery App shopping list could not be refreshed"
            ) from err
