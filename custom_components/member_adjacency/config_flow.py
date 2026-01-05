from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import (
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_ICON,
    CONF_NAME,
    CONF_PROXIMITY_THRESHOLD_M,
    CONF_ROUNDING,
    DEFAULT_ICON,
    DEFAULT_NAME,
    DEFAULT_PROXIMITY_THRESHOLD_M,
    DEFAULT_ROUNDING,
    DOMAIN,
)


def _try_get_coords_from_state(state) -> tuple[float, float] | None:
    """Extract (lat, lon) from a HA State object."""
    if state is None:
        return None

    attrs = state.attributes or {}

    # 1) mobile_app geocoded_location style: attributes["Location"] = [lat, lon]
    loc = attrs.get("Location")
    if isinstance(loc, (list, tuple)) and len(loc) == 2:
        try:
            return (float(loc[0]), float(loc[1]))
        except (TypeError, ValueError):
            return None

    # 2) Common attributes
    if "latitude" in attrs and "longitude" in attrs:
        try:
            return (float(attrs["latitude"]), float(attrs["longitude"]))
        except (TypeError, ValueError):
            return None

    # 3) If state is "lat,lon"
    if isinstance(state.state, str) and "," in state.state:
        parts = [p.strip() for p in state.state.split(",")]
        if len(parts) == 2:
            try:
                return (float(parts[0]), float(parts[1]))
            except (TypeError, ValueError):
                return None

    return None


def _has_coords(hass: HomeAssistant, entity_id: str) -> bool:
    st = hass.states.get(entity_id)
    return _try_get_coords_from_state(st) is not None


class MemberAdjacencyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Member Adjacency."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_a: str = user_input[CONF_ENTITY_A]
            entity_b: str = user_input[CONF_ENTITY_B]

            # Prevent duplicates (order-independent)
            pair = "__".join(sorted([entity_a, entity_b]))
            await self.async_set_unique_id(pair)
            self._abort_if_unique_id_configured()

            if not _has_coords(self.hass, entity_a):
                errors[CONF_ENTITY_A] = "invalid_entity"
            if not _has_coords(self.hass, entity_b):
                errors[CONF_ENTITY_B] = "invalid_entity"

            if not errors:
                title = f"{entity_a} ↔ {entity_b}"
                return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_A): selector.EntitySelector(),
                vol.Required(CONF_ENTITY_B): selector.EntitySelector(),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_ICON, default=DEFAULT_ICON): str,
                vol.Optional(CONF_ROUNDING, default=DEFAULT_ROUNDING): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=3)
                ),
                vol.Optional(
                    CONF_PROXIMITY_THRESHOLD_M, default=DEFAULT_PROXIMITY_THRESHOLD_M
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MemberAdjacencyOptionsFlowHandler(config_entry)


class MemberAdjacencyOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_a: str = user_input[CONF_ENTITY_A]
            entity_b: str = user_input[CONF_ENTITY_B]

            if not _has_coords(self.hass, entity_a):
                errors[CONF_ENTITY_A] = "invalid_entity"
            if not _has_coords(self.hass, entity_b):
                errors[CONF_ENTITY_B] = "invalid_entity"

            if not errors:
                # We store options separately; sensor reads merged values.
                return self.async_create_entry(title="", data=user_input)

        data = {**self._entry.data, **self._entry.options}

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_A, default=data.get(CONF_ENTITY_A)): selector.EntitySelector(),
                vol.Required(CONF_ENTITY_B, default=data.get(CONF_ENTITY_B)): selector.EntitySelector(),
                vol.Optional(CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Optional(CONF_ICON, default=data.get(CONF_ICON, DEFAULT_ICON)): str,
                vol.Optional(CONF_ROUNDING, default=data.get(CONF_ROUNDING, DEFAULT_ROUNDING)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=3)
                ),
                vol.Optional(
                    CONF_PROXIMITY_THRESHOLD_M,
                    default=data.get(CONF_PROXIMITY_THRESHOLD_M, DEFAULT_PROXIMITY_THRESHOLD_M),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
