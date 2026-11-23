"""Dinners calendar tests. Meal data here is example data."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.grocery_app.api import MealRecipe, PlannedMeal
from custom_components.grocery_app.calendar import dinner_events

from .common import (
    MEALS_URL,
    TEST_ACCESS_CLIENT_SECRET,
    TEST_APP_TOKEN,
    assert_secret_headers,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

ENTITY = "calendar.grocery_dinners"


def _recipe(name: str) -> dict[str, Any]:
    return {"id": name.lower().replace(" ", "-"), "name": name, "photo_url": None}


def _meals(today: date) -> list[dict[str, Any]]:
    """Example plan: lunch today, dinner today and in two days, an empty day."""
    return [
        {"date": today.isoformat(), "meal": "lunch", "recipes": [_recipe("Soup")]},
        {
            "date": today.isoformat(),
            "meal": "dinner",
            "recipes": [_recipe("Chicken Tacos"), _recipe("Mexican Rice")],
        },
        {
            "date": (today + timedelta(days=1)).isoformat(),
            "meal": "dinner",
            "recipes": [],
        },
        {
            "date": (today + timedelta(days=2)).isoformat(),
            "meal": "Dinner",
            "recipes": [_recipe("Baked Ziti")],
        },
    ]


def _meal_calls(aioclient_mock: AiohttpClientMocker) -> list[tuple]:
    return [c for c in aioclient_mock.mock_calls if c[1].path == "/api/ha/meals"]


def test_dinner_events_filter_merge_and_skip() -> None:
    """Only dinner slots become events; empty days skip; same-day dinners merge."""
    day = date(2026, 11, 23)
    events = dinner_events(
        [
            PlannedMeal(day, "breakfast", (MealRecipe("1", "Pancakes"),)),
            PlannedMeal(day, "DINNER", (MealRecipe("2", "Tacos"),)),
            PlannedMeal(
                day, "dinner", (MealRecipe("3", "Rice"), MealRecipe("2", "Tacos"))
            ),
            PlannedMeal(day + timedelta(days=1), "dinner", ()),
        ]
    )
    assert len(events) == 1
    event = events[0]
    assert (event.start, event.end) == (day, day + timedelta(days=1))
    assert event.summary == "Tacos + Rice"
    assert event.description == "• Tacos\n• Rice"
    assert event.uid == "grocery_app_dinner_2026-11-23"
    assert event.all_day


async def test_state_shows_tonights_dinner(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Tonight's dinner turns the calendar on and fills its message."""
    today = dt_util.now().date()
    await setup_integration(hass, aioclient_mock, meals=_meals(today))

    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.name == "Grocery Dinners"
    assert state.state == STATE_ON
    assert state.attributes["message"] == "Chicken Tacos + Mexican Rice"
    assert state.attributes["all_day"] is True
    assert hass.states.get("todo.grocery_app") is not None

    call = _meal_calls(aioclient_mock)[0]
    assert_secret_headers(call[3], call[1].with_query(None))
    assert dict(call[1].query) == {
        "start": today.isoformat(),
        "end": (today + timedelta(days=13)).isoformat(),
    }
    for secret in (TEST_APP_TOKEN, TEST_ACCESS_CLIENT_SECRET):
        assert secret not in str(call[1])


async def test_state_shows_next_dinner_when_none_tonight(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With no dinner tonight the state is off and the message is the next one."""
    today = dt_util.now().date()
    await setup_integration(hass, aioclient_mock, meals=_meals(today)[2:])
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["message"] == "Baked Ziti"
    assert state.attributes["start_time"].startswith(
        (today + timedelta(days=2)).isoformat()
    )


async def test_get_events_service(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """calendar.get_events returns all-day dinner events for the range."""
    today = dt_util.now().date()
    await setup_integration(hass, aioclient_mock, meals=_meals(today))
    start = dt_util.start_of_local_day()
    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            ATTR_ENTITY_ID: ENTITY,
            "start_date_time": start,
            "end_date_time": start + timedelta(days=7),
        },
        blocking=True,
        return_response=True,
    )
    events = result[ENTITY]["events"]
    assert [(e["start"], e["end"], e["summary"]) for e in events] == [
        (
            today.isoformat(),
            (today + timedelta(days=1)).isoformat(),
            "Chicken Tacos + Mexican Rice",
        ),
        (
            (today + timedelta(days=2)).isoformat(),
            (today + timedelta(days=3)).isoformat(),
            "Baked Ziti",
        ),
    ]
    last = _meal_calls(aioclient_mock)[-1]
    assert dict(last[1].query) == {
        "start": today.isoformat(),
        "end": (today + timedelta(days=7)).isoformat(),
    }


async def test_long_range_is_chunked(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Ranges over 62 days are split to respect the API limit."""
    entry = await setup_integration(hass, aioclient_mock, meals=[])
    before = len(_meal_calls(aioclient_mock))
    client = entry.runtime_data.client
    start = date(2026, 1, 1)
    await client.async_get_meals(start, start + timedelta(days=99))
    queries = [dict(c[1].query) for c in _meal_calls(aioclient_mock)[before:]]
    assert queries == [
        {"start": "2026-01-01", "end": "2026-03-03"},
        {"start": "2026-03-04", "end": "2026-04-10"},
    ]


async def test_meals_endpoint_missing_does_not_block_the_list(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 404 from the meals endpoint leaves the to-do list loaded."""
    entry = await setup_integration(hass, aioclient_mock, meals_status=404)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("todo.grocery_app").state == "1"
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE
    assert TEST_APP_TOKEN not in caplog.text


async def test_get_events_error_returns_empty(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An API error during get_events is logged and yields no events."""
    today = dt_util.now().date()
    entry = await setup_integration(hass, aioclient_mock, meals=_meals(today))
    aioclient_mock.clear_requests()
    aioclient_mock.get(MEALS_URL, status=404, text=TEST_APP_TOKEN)
    entity = hass.data["calendar"].get_entity(ENTITY)
    start = dt_util.start_of_local_day()
    events = await entity.async_get_events(hass, start, start + timedelta(days=7))
    assert events == []
    assert "could not load planned dinners" in caplog.text
    assert TEST_APP_TOKEN not in caplog.text
    assert entry.state is ConfigEntryState.LOADED


async def test_unexpected_shape_is_rejected(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-list payload makes the calendar unavailable, not broken."""
    aioclient_mock.get(MEALS_URL, json={"unexpected": True})
    await setup_integration(hass, aioclient_mock)
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE
