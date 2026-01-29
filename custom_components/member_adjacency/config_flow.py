"""
Config and options flow for the Member Adjacency component.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_BASE_ENTITY,
    CONF_TRACKER_ENTITY,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_SECONDS,
    CONF_MAX_ACCURACY_M,
    CONF_FORCE_METERS,
    CONF_RESYNC_SILENCE_S,
    CONF_RESYNC_HOLD_S,
    CONF_MAX_SPEED_KMH,
    CONF_MIN_UPDATES_FOR_PROXIMITY,
    CONF_UPDATE_WINDOW_S,
    CONF_REQUIRE_RELIABLE_PROXIMITY,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_FORCE_METERS,
    DEFAULT_RESYNC_SILENCE_S,
    DEFAULT_RESYNC_HOLD_S,
    DEFAULT_MAX_SPEED_KMH,
    DEFAULT_MIN_UPDATES_FOR_PROXIMITY,
    DEFAULT_UPDATE_WINDOW_S,
    DEFAULT_REQUIRE_RELIABLE_PROXIMITY,
    DOMAIN,
)


def _try_get_coords_from_state(state) -> tuple[float, float] | None:
    if state is None:
        return None
    attrs = state.attributes or {}

    loc = attrs.get("Location")
    if isinstance(loc, (list, tuple)) and len(loc) == 2:
        try:
            return (float(loc[0]), float(loc[1]))
        except (TypeError, ValueError):
            return None

    if "latitude" in attrs and "longitude" in attrs:
        try:
            return (float(attrs["latitude"]), float(attrs["longitude"]))
        except (TypeError, ValueError):
            return None

    if isinstance(state.state, str) and "," in state.state:
        parts = [p.strip() for p in state.state.split(",")]
        if len(parts) == 2:
            try:
                return (float(parts[0]), float(parts[1]))
            except (TypeError, ValueError):
                return None

    return None


def _device_name_for_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    ent = ent_reg.async_get(entity_id)
    if ent and ent.device_id:
        dev = dev_reg.async_get(ent.device_id)
        if dev:
            return dev.name_by_user or dev.name
    return None


def _friendly_or_entity(hass: HomeAssistant, entity_id: str) -> str:
    st = hass.states.get(entity_id)
    if st and (st.attributes or {}).get("friendly_name"):
        return str(st.attributes["friendly_name"])
    return entity_id


class MemberAdjacencyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Member Adjacency."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            a = user_input.get(CONF_BASE_ENTITY)
            b = user_input.get(CONF_TRACKER_ENTITY)

            if a == b:
                errors[CONF_TRACKER_ENTITY] = "same_entity"

            if not errors:
                if _try_get_coords_from_state(self.hass.states.get(a)) is None:
                    errors[CONF_BASE_ENTITY] = "invalid_entity"
                if _try_get_coords_from_state(self.hass.states.get(b)) is None:
                    errors[CONF_TRACKER_ENTITY] = "invalid_entity"

            entry_th = int(user_input.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
            exit_th = int(user_input.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"

            if not errors:
                pair = "__".join(sorted([a, b]))
                await self.async_set_unique_id(pair)
                self._abort_if_unique_id_configured()

                base_name = _device_name_for_entity(self.hass, a) or _friendly_or_entity(self.hass, a)
                tracker_name = _device_name_for_entity(self.hass, b) or _friendly_or_entity(self.hass, b)
                title = f"{tracker_name} → {base_name}"

                data_to_store = {
                    CONF_BASE_ENTITY: a,
                    CONF_TRACKER_ENTITY: b,
                    CONF_ENTITY_A: a,
                    CONF_ENTITY_B: b,
                    CONF_ENTRY_THRESHOLD_M: user_input.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M),
                    CONF_EXIT_THRESHOLD_M: user_input.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M),
                    CONF_DEBOUNCE_SECONDS: user_input.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS),
                    CONF_MAX_ACCURACY_M: user_input.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M),
                    CONF_FORCE_METERS: user_input.get(CONF_FORCE_METERS, DEFAULT_FORCE_METERS),
                    CONF_RESYNC_SILENCE_S: user_input.get(CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S),
                    CONF_RESYNC_HOLD_S: user_input.get(CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S),
                    CONF_MAX_SPEED_KMH: user_input.get(CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH),
                    CONF_MIN_UPDATES_FOR_PROXIMITY: user_input.get(CONF_MIN_UPDATES_FOR_PROXIMITY, DEFAULT_MIN_UPDATES_FOR_PROXIMITY),
                    CONF_UPDATE_WINDOW_S: user_input.get(CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S),
                    CONF_REQUIRE_RELIABLE_PROXIMITY: user_input.get(CONF_REQUIRE_RELIABLE_PROXIMITY, DEFAULT_REQUIRE_RELIABLE_PROXIMITY),
                }

                return self.async_create_entry(title=title, data=data_to_store)

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "device_tracker", "person", "zone"],
                    )
                ),
                vol.Required(CONF_TRACKER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "device_tracker", "person", "zone"],
                    )
                ),
                vol.Required(CONF_ENTRY_THRESHOLD_M, default=DEFAULT_ENTRY_THRESHOLD_M): vol.Coerce(int),
                vol.Required(CONF_EXIT_THRESHOLD_M, default=DEFAULT_EXIT_THRESHOLD_M): vol.Coerce(int),
                vol.Required(CONF_DEBOUNCE_SECONDS, default=DEFAULT_DEBOUNCE_SECONDS): vol.Coerce(int),
                vol.Required(CONF_MAX_ACCURACY_M, default=DEFAULT_MAX_ACCURACY_M): vol.Coerce(int),
                vol.Required(CONF_FORCE_METERS, default=DEFAULT_FORCE_METERS): bool,
                vol.Required(CONF_RESYNC_SILENCE_S, default=DEFAULT_RESYNC_SILENCE_S): vol.Coerce(int),
                vol.Required(CONF_RESYNC_HOLD_S, default=DEFAULT_RESYNC_HOLD_S): vol.Coerce(int),
                vol.Required(CONF_MAX_SPEED_KMH, default=DEFAULT_MAX_SPEED_KMH): vol.Coerce(int),
                vol.Required(CONF_MIN_UPDATES_FOR_PROXIMITY, default=DEFAULT_MIN_UPDATES_FOR_PROXIMITY): vol.Coerce(int),
                vol.Required(CONF_UPDATE_WINDOW_S, default=DEFAULT_UPDATE_WINDOW_S): vol.Coerce(int),
                vol.Required(CONF_REQUIRE_RELIABLE_PROXIMITY, default=DEFAULT_REQUIRE_RELIABLE_PROXIMITY): bool,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return MemberAdjacencyOptionsFlow(config_entry)


class MemberAdjacencyOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Member Adjacency."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        errors: dict[str, str] = {}
        data = {**self._entry.data, **self._entry.options}

        if user_input is not None:
            entry_th = int(user_input.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
            exit_th = int(user_input.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTRY_THRESHOLD_M, default=data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)): vol.Coerce(int),
                vol.Required(CONF_EXIT_THRESHOLD_M, default=data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)): vol.Coerce(int),
                vol.Required(CONF_DEBOUNCE_SECONDS, default=data.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)): vol.Coerce(int),
                vol.Required(CONF_MAX_ACCURACY_M, default=data.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M)): vol.Coerce(int),
                vol.Required(CONF_FORCE_METERS, default=data.get(CONF_FORCE_METERS, DEFAULT_FORCE_METERS)): bool,
                vol.Required(CONF_RESYNC_SILENCE_S, default=data.get(CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S)): vol.Coerce(int),
                vol.Required(CONF_RESYNC_HOLD_S, default=data.get(CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S)): vol.Coerce(int),
                vol.Required(CONF_MAX_SPEED_KMH, default=data.get(CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH)): vol.Coerce(int),
                vol.Required(CONF_MIN_UPDATES_FOR_PROXIMITY, default=data.get(CONF_MIN_UPDATES_FOR_PROXIMITY, DEFAULT_MIN_UPDATES_FOR_PROXIMITY)): vol.Coerce(int),
                vol.Required(CONF_UPDATE_WINDOW_S, default=data.get(CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S)): vol.Coerce(int),
                vol.Required(CONF_REQUIRE_RELIABLE_PROXIMITY, default=data.get(CONF_REQUIRE_RELIABLE_PROXIMITY, DEFAULT_REQUIRE_RELIABLE_PROXIMITY)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
