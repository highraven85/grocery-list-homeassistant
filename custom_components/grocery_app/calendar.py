"""Calendar entity showing planned dinners from the Grocery App meal plan."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import override

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import GroceryAppError, PlannedMeal
from .const import DINNER_MEAL, DINNERS_ENTITY_ID, DINNERS_NAME, DINNERS_UNIQUE_ID
from .coordinator import GroceryAppConfigEntry, GroceryAppMealsCoordinator

_LOGGER = logging.getLogger(__name__)

SUMMARY_SEPARATOR = " + "


def dinner_events(meals: Iterable[PlannedMeal]) -> list[CalendarEvent]:
    """Build one all-day event per day that has dinner recipes.

    Other meal slots and days without recipes are skipped. Two dinner entries
    for the same day are merged, keeping recipe order and dropping duplicates.
    """
    by_day: dict[date, list[str]] = {}
    for meal in meals:
        if meal.meal.casefold() != DINNER_MEAL:
            continue
        names = by_day.setdefault(meal.date, [])
        for recipe in meal.recipes:
            if recipe.name not in names:
                names.append(recipe.name)
    events = []
    for day in sorted(by_day):
        names = by_day[day]
        if not names:
            continue
        events.append(
            CalendarEvent(
                start=day,
                end=day + timedelta(days=1),
                summary=SUMMARY_SEPARATOR.join(names),
                description="\n".join(f"• {name}" for name in names),
                uid=f"grocery_app_dinner_{day.isoformat()}",
            )
        )
    return events


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GroceryAppConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Grocery Dinners calendar."""
    coordinator = GroceryAppMealsCoordinator(hass, entry, entry.runtime_data.client)
    # A plain refresh, not first_refresh: if the meals endpoint is down or not
    # deployed, the shopping list still loads and the calendar retries later.
    await coordinator.async_refresh()
    async_add_entities([GroceryDinnersCalendarEntity(coordinator)])


class GroceryDinnersCalendarEntity(
    CoordinatorEntity[GroceryAppMealsCoordinator], CalendarEntity
):
    """Dinners planned in the grocery app, as all-day events."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:silverware-fork-knife"
    _attr_name = DINNERS_NAME

    def __init__(self, coordinator: GroceryAppMealsCoordinator) -> None:
        """Create the single dinners calendar."""
        super().__init__(coordinator)
        self._attr_unique_id = DINNERS_UNIQUE_ID
        self.entity_id = DINNERS_ENTITY_ID

    @property
    @override
    def event(self) -> CalendarEvent | None:
        """Return tonight's dinner, or the next planned one."""
        today = dt_util.now().date()
        for event in dinner_events(self.coordinator.data or ()):
            if event.end > today:
                return event
        return None

    @override
    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return dinners that overlap the requested range.

        Errors are logged and an empty list is returned so the calendar card
        stays usable.
        """
        first_day = dt_util.as_local(start_date).date()
        last_day = dt_util.as_local(end_date).date()
        try:
            meals = await self.coordinator.client.async_get_meals(first_day, last_day)
        except GroceryAppError:
            _LOGGER.error("Grocery App could not load planned dinners")
            return []
        start_local = dt_util.as_local(start_date)
        end_local = dt_util.as_local(end_date)
        return [
            event
            for event in dinner_events(meals)
            if event.start_datetime_local < end_local
            and event.end_datetime_local > start_local
        ]
