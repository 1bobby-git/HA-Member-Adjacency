from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import (
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_SECONDS,
    CONF_MAX_ACCURACY_M,
    CONF_FORCE_METERS,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_FORCE_METERS,
    DOMAIN,
    GEO_SUFFIX,
)


def _geocoded_candidates(hass: HomeAssistant) -> list[str]:
    out: list[str] = []
    for st in hass.states.async_all("sensor"):
        if st.entity_id.endswith(GEO_SUFFIX):
            out.append(st.entity_id)
    out.sort()
    return out


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


def _has_coords(hass: HomeAssistant, entity_id: str) -> bool:
    return _try_get_coords_from_state(hass.states.get(entity_id)) is not None


class MemberAdjacencyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        candidates = _geocoded_candidates(self.hass)
        default_a = candidates[0] if len(candidates) >= 1 else None
        default_b = candidates[1] if len(candidates) >= 2 else None

        if user_input is not None:
            a = user_input[CONF_ENTITY_A]
            b = user_input[CONF_ENTITY_B]

            if a == b:
                errors[CONF_ENTITY_B] = "same_entity"

            if candidates:
                if not a.endswith(GEO_SUFFIX):
                    errors[CONF_ENTITY_A] = "not_geocoded"
                if not b.endswith(GEO_SUFFIX):
                    errors[CONF_ENTITY_B] = "not_geocoded"

            if not errors and not _has_coords(self.hass, a):
                errors[CONF_ENTITY_A] = "invalid_entity"
            if not errors and not _has_coords(self.hass, b):
                errors[CONF_ENTITY_B] = "invalid_entity"

            entry_th = int(user_input[CONF_ENTRY_THRESHOLD_M])
            exit_th = int(user_input[CONF_EXIT_THRESHOLD_M])
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"

            if not errors:
                # unique per pair (order-independent)
                pair = "__".join(sorted([a, b]))
                await self.async_set_unique_id(pair)
                self._abort_if_unique_id_configured()

                title = f"{a} ↔ {b}"
                return self.async_create_entry(title=title, data=user_input)

        if candidates:
            sel = selector.SelectSelectorConfig(
                options=candidates, mode=selector.SelectSelectorMode.DROPDOWN
            )
            entity_sel_a = selector.SelectSelector(sel)
            entity_sel_b = selector.SelectSelector(sel)
        else:
            entity_sel_a = selector.EntitySelector()
            entity_sel_b = selector.EntitySelector()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_A, default=default_a): entity_sel_a,
                vol.Required(CONF_ENTITY_B, default=default_b): entity_sel_b,
                vol.Required(CONF_ENTRY_THRESHOLD_M, default=DEFAULT_ENTRY_THRESHOLD_M): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Required(CONF_EXIT_THRESHOLD_M, default=DEFAULT_EXIT_THRESHOLD_M): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Optional(CONF_DEBOUNCE_SECONDS, default=DEFAULT_DEBOUNCE_SECONDS): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=60)
                ),
                vol.Optional(CONF_MAX_ACCURACY_M, default=DEFAULT_MAX_ACCURACY_M): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=10_000)
                ),
                vol.Optional(CONF_FORCE_METERS, default=DEFAULT_FORCE_METERS): bool,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MemberAdjacencyOptionsFlow(config_entry)


class MemberAdjacencyOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        data = {**self._entry.data, **self._entry.options}

        if user_input is not None:
            entry_th = int(user_input.get(CONF_ENTRY_THRESHOLD_M, data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)))
            exit_th = int(user_input.get(CONF_EXIT_THRESHOLD_M, data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)))
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(CONF_ENTRY_THRESHOLD_M, default=data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Optional(CONF_EXIT_THRESHOLD_M, default=data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Optional(CONF_DEBOUNCE_SECONDS, default=data.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=60)
                ),
                vol.Optional(CONF_MAX_ACCURACY_M, default=data.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=10_000)
                ),
                vol.Optional(CONF_FORCE_METERS, default=data.get(CONF_FORCE_METERS, DEFAULT_FORCE_METERS)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
