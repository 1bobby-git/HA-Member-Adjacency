from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import (
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_PROXIMITY_THRESHOLD_M,
    DEFAULT_PROXIMITY_THRESHOLD_M,
    DOMAIN,
    GEO_SUFFIX,
)


def _try_get_coords_from_state(state) -> tuple[float, float] | None:
    """Extract (lat, lon) from a HA State object."""
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
    st = hass.states.get(entity_id)
    return _try_get_coords_from_state(st) is not None


def _geocoded_candidates(hass: HomeAssistant) -> list[str]:
    """Return sensor entity_ids ending with _geocoded_location."""
    out: list[str] = []
    for st in hass.states.async_all("sensor"):
        if st.entity_id.endswith(GEO_SUFFIX):
            out.append(st.entity_id)
    out.sort()
    return out


class MemberAdjacencyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for 인접센서."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        candidates = _geocoded_candidates(self.hass)
        default_a = candidates[0] if len(candidates) >= 1 else None
        default_b = candidates[1] if len(candidates) >= 2 else None

        if user_input is not None:
            entity_a: str = user_input[CONF_ENTITY_A]
            entity_b: str = user_input[CONF_ENTITY_B]

            pair = "__".join(sorted([entity_a, entity_b]))
            await self.async_set_unique_id(pair)
            self._abort_if_unique_id_configured()

            if not entity_a.endswith(GEO_SUFFIX):
                errors[CONF_ENTITY_A] = "not_geocoded"
            if not entity_b.endswith(GEO_SUFFIX):
                errors[CONF_ENTITY_B] = "not_geocoded"

            if not errors and not _has_coords(self.hass, entity_a):
                errors[CONF_ENTITY_A] = "invalid_entity"
            if not errors and not _has_coords(self.hass, entity_b):
                errors[CONF_ENTITY_B] = "invalid_entity"

            if not errors:
                title = f"{entity_a} ↔ {entity_b}"
                return self.async_create_entry(title=title, data=user_input)

        # Build selector schema:
        # - If geocoded candidates exist, show only those via SelectSelector.
        # - Otherwise fallback to EntitySelector.
        if candidates:
            entity_selector_a = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=candidates,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            entity_selector_b = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=candidates,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

            schema = vol.Schema(
                {
                    vol.Required(CONF_ENTITY_A, default=default_a): entity_selector_a,
                    vol.Required(CONF_ENTITY_B, default=default_b): entity_selector_b,
                    vol.Optional(
                        CONF_PROXIMITY_THRESHOLD_M,
                        default=DEFAULT_PROXIMITY_THRESHOLD_M,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_ENTITY_A): selector.EntitySelector(),
                    vol.Required(CONF_ENTITY_B): selector.EntitySelector(),
                    vol.Optional(
                        CONF_PROXIMITY_THRESHOLD_M,
                        default=DEFAULT_PROXIMITY_THRESHOLD_M,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
                }
            )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MemberAdjacencyOptionsFlowHandler(config_entry)


class MemberAdjacencyOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow (threshold only)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        candidates = _geocoded_candidates(self.hass)
        data = {**self._entry.data, **self._entry.options}

        if user_input is not None:
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PROXIMITY_THRESHOLD_M,
                    default=data.get(CONF_PROXIMITY_THRESHOLD_M, DEFAULT_PROXIMITY_THRESHOLD_M),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
            }
        )

        # If candidates exist, also show current entity_a/b as read-only info in attributes only
        # (Options flow keeps UX minimal: threshold only as requested)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
