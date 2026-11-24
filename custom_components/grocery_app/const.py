"""Constants for the Grocery App integration."""

from datetime import timedelta
from typing import Final

from homeassistant.const import CONF_URL

DOMAIN: Final = "grocery_app"
DEFAULT_NAME: Final = "Grocaroo"
ENTITY_UNIQUE_ID: Final = "grocery_app"
ENTITY_ID: Final = "todo.grocery_app"

DINNERS_NAME: Final = "Grocaroo Dinners"
DINNERS_UNIQUE_ID: Final = "grocery_app_dinners"
DINNERS_ENTITY_ID: Final = "calendar.grocery_dinners"
DINNER_MEAL: Final = "dinner"

CONF_ACCESS_CLIENT_ID: Final = "access_client_id"
CONF_ACCESS_CLIENT_SECRET: Final = "access_client_secret"
CONF_APP_TOKEN: Final = "app_token"

# Re-exported so the integration has one place that lists stored config keys.
CONFIG_KEYS: Final = (
    CONF_URL,
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_APP_TOKEN,
)

SCAN_INTERVAL: Final = timedelta(seconds=30)
MEALS_SCAN_INTERVAL: Final = timedelta(minutes=15)
# Days of upcoming meals the calendar keeps for its state and "next dinner".
MEALS_LOOKAHEAD_DAYS: Final = 14
# The meals endpoint accepts at most this many days per request.
MEALS_MAX_DAYS: Final = 62
# The card's meals websocket command accepts at most this many days.
WS_MEALS_MAX_DAYS: Final = 92

# Recipe photo proxy, served by Home Assistant with Home Assistant auth.
PHOTO_URL_PREFIX: Final = "/api/grocery_app/recipe_photo"
PHOTO_CACHE_LIMIT: Final = 500
PHOTO_MAX_BYTES: Final = 5 * 1024 * 1024

# Bundled Lovelace card.
CARD_URL_BASE: Final = "/grocery_app_static"
CARD_FILENAME: Final = "grocery-app-card.js"

ATTR_DEPARTMENT_ORDER: Final = "department_order"
ATTR_ITEM_DEPARTMENTS: Final = "item_departments"

API_STATUS_NEEDS_ACTION: Final = "needs_action"
API_STATUS_COMPLETED: Final = "completed"
API_STATUSES: Final = frozenset({API_STATUS_NEEDS_ACTION, API_STATUS_COMPLETED})
