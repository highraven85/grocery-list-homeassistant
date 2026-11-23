"""Recipe photo proxy so the dashboard can show photos without app credentials."""

from __future__ import annotations

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.http import KEY_HASS

from .api import GroceryAppError
from .const import PHOTO_URL_PREFIX
from .websocket import loaded_client


class GroceryAppRecipePhotoView(HomeAssistantView):
    """Serve a recipe photo to signed-in Home Assistant users.

    The image tag uses a signed path (auth/sign_path), so no token is placed in
    the page. The app credentials stay inside Home Assistant.
    """

    url = PHOTO_URL_PREFIX + "/{recipe_id}"
    name = "api:grocery_app:recipe_photo"
    requires_auth = True

    async def get(self, request: web.Request, recipe_id: str) -> web.StreamResponse:
        """Return the photo bytes, or 404 when the recipe has no known photo."""
        client = loaded_client(request.app[KEY_HASS])
        if client is None or not client.has_photo(recipe_id):
            return web.Response(status=404)
        try:
            body, content_type = await client.async_get_recipe_photo(recipe_id)
        except GroceryAppError:
            return web.Response(status=502)
        return web.Response(
            body=body,
            content_type=content_type,
            headers={"Cache-Control": "private, max-age=86400"},
        )
