"""To-do list entity for the Grocery App shopping list."""

from __future__ import annotations

import logging
from typing import override

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    GroceryAppAuthError,
    GroceryAppConnectionError,
    GroceryAppError,
    GroceryList,
)
from .const import (
    API_STATUS_COMPLETED,
    API_STATUS_NEEDS_ACTION,
    DEFAULT_NAME,
    DOMAIN,
    ENTITY_ID,
    ENTITY_UNIQUE_ID,
)
from .coordinator import GroceryAppConfigEntry, GroceryAppCoordinator

_LOGGER = logging.getLogger(__name__)

_STATUS_TO_API = {
    TodoItemStatus.NEEDS_ACTION: API_STATUS_NEEDS_ACTION,
    TodoItemStatus.COMPLETED: API_STATUS_COMPLETED,
}


def _service_error(err: GroceryAppError) -> HomeAssistantError:
    """Map a client error to a Home Assistant error that does not include secrets."""
    if isinstance(err, GroceryAppAuthError):
        key = "auth_failed"
    elif isinstance(err, GroceryAppConnectionError):
        key = "cannot_connect"
    else:
        key = "request_failed"
    return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GroceryAppConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Grocery App to-do entity."""
    async_add_entities([GroceryAppTodoListEntity(entry.runtime_data)])


class GroceryAppTodoListEntity(
    CoordinatorEntity[GroceryAppCoordinator], TodoListEntity
):
    """A shopping list backed by the grocery app API."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:cart"
    _attr_name = DEFAULT_NAME
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: GroceryAppCoordinator) -> None:
        """Create the single Grocery App list."""
        super().__init__(coordinator)
        self._attr_unique_id = ENTITY_UNIQUE_ID
        # A valid entity id of this platform's domain is how Home Assistant
        # records the suggested object id. The friendly name is Grocery App,
        # which also slugifies to grocery_app.
        self.entity_id = ENTITY_ID
        self._apply_items(coordinator.data)

    @callback
    def _apply_items(self, data: GroceryList | None) -> None:
        """Copy coordinator data into the to-do list."""
        if data is None:
            self._attr_todo_items = None
            return
        self._attr_todo_items = [
            TodoItem(
                uid=item.id,
                summary=item.name,
                status=TodoItemStatus(item.status),
                description=item.description,
            )
            for item in data.items
        ]

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Refresh items when the coordinator fetches the list."""
        self._apply_items(self.coordinator.data)
        super()._handle_coordinator_update()

    @override
    async def async_added_to_hass(self) -> None:
        """Publish the list that was fetched before the entity was added."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    @override
    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add an item."""
        name = (item.summary or "").strip()
        if not name:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="item_name_required",
            )
        try:
            await self.coordinator.client.async_add_item(name)
        except GroceryAppError as err:
            _LOGGER.error("Grocery App could not add an item")
            raise _service_error(err) from err
        await self.coordinator.async_refresh()

    @override
    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Rename an item or change its completed status."""
        if not item.uid:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="item_id_required",
            )
        name = item.summary.strip() if item.summary is not None else None
        if item.summary is not None and not name:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="item_name_required",
            )
        status = _STATUS_TO_API.get(item.status) if item.status is not None else None
        if item.status is not None and status is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="item_update_empty",
            )
        if name is None and status is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="item_update_empty",
            )
        try:
            await self.coordinator.client.async_update_item(
                item.uid,
                name=name,
                status=status,
            )
        except GroceryAppError as err:
            _LOGGER.error("Grocery App could not update an item")
            raise _service_error(err) from err
        await self.coordinator.async_refresh()

    @override
    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Remove every requested item."""
        failure: GroceryAppError | None = None
        for uid in uids:
            try:
                await self.coordinator.client.async_delete_item(uid)
            except GroceryAppError as err:
                _LOGGER.error("Grocery App could not remove an item")
                failure = err
                break
        await self.coordinator.async_refresh()
        if failure is not None:
            raise _service_error(failure) from failure
