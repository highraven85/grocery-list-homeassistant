# Grocery App

Home Assistant custom integration that connects a grocery-list HTTP API to a to-do list entity and a dinners calendar.

The entity is `todo.grocery_app`, named **Grocery App**. Use the built-in to-do list card, and the built-in Assist to-do intents, to add, complete, and remove items. This is a custom integration. It is not a Home Assistant add-on, and it is not a REST sensor.

The integration also adds `calendar.grocery_dinners`, named **Grocery Dinners**. It shows each day's planned dinner from the grocery app meal plan as an all-day event. The event title is the recipe names joined with ` + `, and the description lists the recipes. Breakfast, lunch, snacks, and days without recipes are left out. The calendar is on while tonight's dinner is planned, and its `message` attribute holds tonight's or the next planned dinner. Use the built-in calendar card to show it.

This project is not an official Home Assistant product and it is not an official Cloudflare product.

## Requirements

- Home Assistant Core 2026.10.4 or newer
- [HACS](https://www.hacs.xyz/) 2.0.5 or newer
- A grocery app that implements the HTTP API below
- A Cloudflare Access service token (client id and client secret) and the grocery app API token

Home Assistant must be able to reach the grocery app base URL.

## Install with HACS

1. In Home Assistant, open **HACS**.
2. Open the three-dot menu in the upper-right corner and choose **Custom repositories**.
3. Enter the URL of this repository: `https://github.com/highraven85/grocery-list-homeassistant`
4. Set the category to **Integration** and click **Add**.
5. In the HACS integrations list, find **Grocery App** and download it.
6. Restart Home Assistant.
7. Go to **Settings → Devices & services**.
8. Click **Add integration**, search for **Grocery App**, and open it.
9. Enter the grocery app base URL, the Cloudflare Access client id, the Cloudflare Access client secret, and the app API token.

There is no YAML configuration. Credentials are entered only in this config flow and are stored in the Home Assistant config entry. They are sent as request headers and are never placed in the URL.

Only one Grocery App entry is supported, so the to-do list stays on the entity id `todo.grocery_app` and the calendar on `calendar.grocery_dinners`.

## Configuration fields

| Field | How it is sent |
| --- | --- |
| Base URL | Origin of the grocery app, for example `https://example.com`. Do not include a username, password, or query string. |
| Access client ID | `CF-Access-Client-Id` header |
| Access client secret | `CF-Access-Client-Secret` header |
| App API token | `Authorization: Bearer` header |

All three credentials are password fields. If authentication later fails, Home Assistant starts a reauthentication flow. The integration page can also reconfigure the base URL and credentials.

The integration polls the list about every 30 seconds and upcoming dinners (the next 14 days) about every 15 minutes. The calendar card loads the range it shows when it opens. Adding, completing, renaming, and removing items are sent when the to-do action runs.

## API

The integration calls these paths under the configured base URL:

- `GET /api/ha/todo` returns the current list
- `POST /api/ha/todo/items` with `{ "name": "..." }` adds an item
- `PATCH /api/ha/todo/items/{id}` with optional `name` and `status` renames, completes, or reopens an item
- `DELETE /api/ha/todo/items/{id}` removes an item
- `GET /api/ha/meals?start=YYYY-MM-DD&end=YYYY-MM-DD` returns planned meals (dates inclusive, at most 62 days per request; longer ranges are split)

`status` is `needs_action` or `completed`. `GET /api/ha/todo` looks like this:

```json
{
  "name": "Shopping list",
  "items": [
    {
      "id": "1",
      "name": "Milk",
      "status": "needs_action",
      "description": "Optional note"
    }
  ]
}
```

`GET /api/ha/meals` returns a list, one entry per day and meal slot:

```json
[
  {
    "date": "2026-11-23",
    "meal": "dinner",
    "recipes": [{ "id": "r1", "name": "Chicken Tacos", "photo_url": null }]
  }
]
```

Only entries whose `meal` is `dinner` (any letter case) become calendar events. Date and slot query values are the only data placed in a URL.

`description` is optional. The Home Assistant entity name stays **Grocery App** even when the payload uses a different list name.

Requests send `CF-Access-Client-Id`, `CF-Access-Client-Secret`, and `Authorization: Bearer`. A failed credential check is reported in the config flow and in the Home Assistant log without the credential values. Transient connection and server errors are retried.

## Diagnostics

Diagnostics downloaded from **Settings → Devices & services** redact the base URL and the credentials.

## Changelog

- **1.1.0**: Adds the `calendar.grocery_dinners` calendar for planned dinners from `GET /api/ha/meals`. If the meals endpoint fails, the calendar is unavailable and the to-do list keeps working.
- **1.0.0**: First release with the `todo.grocery_app` shopping list.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). Tests mock the HTTP API.

## License

MIT. See [LICENSE](LICENSE).
