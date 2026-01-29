"""
Config and options flow for the Member Adjacency component.

This flow allows a user to configure two location-providing entities and
adjust various thresholds affecting proximity detection.  It has been
extended to include configuration for movement filtering and delayed
update resynchronisation.  These settings allow false positives to be
reduced when GPS updates arrive late or jump unexpectedly.
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
    GEO_SUFFIX,
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


def _label_for_entity(hass: HomeAssistant, entity_id: str) -> str:
    dev_name = _device_name_for_entity(hass, entity_id)
    if dev_name:
        return f"{dev_name} ({entity_id})"
    fn = _friendly_or_entity(hass, entity_id)
    if fn != entity_id:
        return f"{fn} ({entity_id})"
    return entity_id


def _group_name(entity_id: str) -> str:
    if entity_id.startswith("sensor.") and entity_id.endswith(GEO_SUFFIX):
        return "Geocoded"
    if entity_id.startswith("device_tracker."):
        return "Device Tracker"
    if entity_id.startswith("person."):
        return "Person"
    if entity_id.startswith("zone."):
        return "Zone"
    if entity_id.startswith("sensor."):
        return "Sensor"
    return "Other"


def _group_order(group: str) -> int:
    order = {
        "Geocoded": 0,
        "Device Tracker": 1,
        "Person": 2,
        "Zone": 3,
        "Sensor": 4,
        "Other": 9,
    }
    return order.get(group, 9)


def _candidate_entities_grouped(hass: HomeAssistant) -> list[dict[str, str]]:
    """
    Return a list of selectable location entities grouped and sorted for display.

    - Only entities with coordinates are included.
    - Sorted by group and then by a friendly label.
    - Each option is a dict with 'value' and 'label'.
    """
    entities: list[str] = []

    for domain in ("sensor", "device_tracker", "person", "zone"):
        for st in hass.states.async_all(domain):
            if st.state in ("unknown", "unavailable"):
                continue
            if _try_get_coords_from_state(st) is None:
                continue
            entities.append(st.entity_id)

    unique = sorted(set(entities))

    rows: list[tuple[int, str, str, str]] = []
    for eid in unique:
        g = _group_name(eid)
        base_label = _label_for_entity(hass, eid)  # label used for sorting within group
        label = f"{g} · {base_label}"
        rows.append((_group_order(g), base_label, label, eid))

    rows.sort(key=lambda x: (x[0], x[1]))
    return [{"value": eid, "label": label} for _, _, label, eid in rows]


def _num_box(min_v: int, max_v: int, step: int, unit: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_v,
            max=max_v,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _num_slider(min_v: int, max_v: int, step: int, unit: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_v,
            max=max_v,
            step=step,
            mode=selector.NumberSelectorMode.SLIDER,
            unit_of_measurement=unit,
        )
    )


class MemberAdjacencyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        options = _candidate_entities_grouped(self.hass)
        candidates = [o["value"] for o in options]

        default_a = candidates[0] if len(candidates) >= 1 else None
        default_b = candidates[1] if len(candidates) >= 2 else None

        if user_input is not None:
            # Support both new (base/tracker) and legacy (entity_a/entity_b) keys
            a = user_input.get(CONF_BASE_ENTITY) or user_input.get(CONF_ENTITY_A)
            b = user_input.get(CONF_TRACKER_ENTITY) or user_input.get(CONF_ENTITY_B)

            if a == b:
                errors[CONF_TRACKER_ENTITY] = "same_entity"

            if not errors:
                if _try_get_coords_from_state(self.hass.states.get(a)) is None:
                    errors[CONF_BASE_ENTITY] = "invalid_entity"
                if _try_get_coords_from_state(self.hass.states.get(b)) is None:
                    errors[CONF_TRACKER_ENTITY] = "invalid_entity"

            entry_th = int(user_input[CONF_ENTRY_THRESHOLD_M])
            exit_th = int(user_input[CONF_EXIT_THRESHOLD_M])
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"

            if not errors:
                # Use a stable unique_id so the same two entities cannot be configured multiple times
                pair = "__".join(sorted([a, b]))
                await self.async_set_unique_id(pair)
                self._abort_if_unique_id_configured()

                base_name = _device_name_for_entity(self.hass, a) or _friendly_or_entity(self.hass, a)
                tracker_name = _device_name_for_entity(self.hass, b) or _friendly_or_entity(self.hass, b)
                title = f"{tracker_name} → {base_name}"

                # Store with new semantic keys (base/tracker), plus legacy keys for compatibility
                data_to_store = {
                    CONF_BASE_ENTITY: a,
                    CONF_TRACKER_ENTITY: b,
                    # Legacy keys for backward compatibility
                    CONF_ENTITY_A: a,
                    CONF_ENTITY_B: b,
                    **{k: v for k, v in user_input.items() if k not in (CONF_BASE_ENTITY, CONF_TRACKER_ENTITY, CONF_ENTITY_A, CONF_ENTITY_B)},
                }

                return self.async_create_entry(title=title, data=data_to_store)

        entity_sel = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        # For initial setup ask the user for all proximity and movement settings
        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_ENTITY, default=default_a): entity_sel,
                vol.Required(CONF_TRACKER_ENTITY, default=default_b): entity_sel,
                vol.Required(CONF_ENTRY_THRESHOLD_M, default=DEFAULT_ENTRY_THRESHOLD_M): _num_box(
                    0, 1_000_000, 10, "m"
                ),
                vol.Required(CONF_EXIT_THRESHOLD_M, default=DEFAULT_EXIT_THRESHOLD_M): _num_box(
                    0, 1_000_000, 10, "m"
                ),
                vol.Required(CONF_DEBOUNCE_SECONDS, default=DEFAULT_DEBOUNCE_SECONDS): _num_slider(
                    0, 60, 1, "s"
                ),
                vol.Required(CONF_MAX_ACCURACY_M, default=DEFAULT_MAX_ACCURACY_M): _num_box(
                    0, 10_000, 10, "m"
                ),
                vol.Required(CONF_FORCE_METERS, default=DEFAULT_FORCE_METERS): selector.BooleanSelector(),
                vol.Required(CONF_RESYNC_SILENCE_S, default=DEFAULT_RESYNC_SILENCE_S): _num_box(
                    0, 86_400, 60, "s"
                ),
                vol.Required(CONF_RESYNC_HOLD_S, default=DEFAULT_RESYNC_HOLD_S): _num_box(
                    0, 600, 5, "s"
                ),
                vol.Required(CONF_MAX_SPEED_KMH, default=DEFAULT_MAX_SPEED_KMH): _num_box(
                    0, 1_000, 10, "km/h"
                ),
                vol.Required(CONF_MIN_UPDATES_FOR_PROXIMITY, default=DEFAULT_MIN_UPDATES_FOR_PROXIMITY): _num_slider(
                    1, 10, 1
                ),
                vol.Required(CONF_UPDATE_WINDOW_S, default=DEFAULT_UPDATE_WINDOW_S): _num_box(
                    60, 1800, 30, "s"
                ),
                vol.Required(CONF_REQUIRE_RELIABLE_PROXIMITY, default=DEFAULT_REQUIRE_RELIABLE_PROXIMITY): selector.BooleanSelector(),
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
        # Merge data and options so we always have a baseline for defaults
        data = {**self._entry.data, **self._entry.options}

        if user_input is not None:
            entry_th = int(user_input.get(CONF_ENTRY_THRESHOLD_M, data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)))
            exit_th = int(user_input.get(CONF_EXIT_THRESHOLD_M, data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)))
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Define the options form with all configurable values
        schema = vol.Schema(
            {
                vol.Required(CONF_ENTRY_THRESHOLD_M, default=data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)): _num_box(
                    0, 1_000_000, 10, "m"
                ),
                vol.Required(CONF_EXIT_THRESHOLD_M, default=data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)): _num_box(
                    0, 1_000_000, 10, "m"
                ),
                vol.Required(CONF_DEBOUNCE_SECONDS, default=data.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)): _num_slider(
                    0, 60, 1, "s"
                ),
                vol.Required(CONF_MAX_ACCURACY_M, default=data.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M)): _num_box(
                    0, 10_000, 10, "m"
                ),
                vol.Required(CONF_FORCE_METERS, default=data.get(CONF_FORCE_METERS, DEFAULT_FORCE_METERS)): selector.BooleanSelector(),
                vol.Required(CONF_RESYNC_SILENCE_S, default=data.get(CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S)): _num_box(
                    0, 86_400, 60, "s"
                ),
                vol.Required(CONF_RESYNC_HOLD_S, default=data.get(CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S)): _num_box(
                    0, 600, 5, "s"
                ),
                vol.Required(CONF_MAX_SPEED_KMH, default=data.get(CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH)): _num_box(
                    0, 1_000, 10, "km/h"
                ),
                vol.Required(CONF_MIN_UPDATES_FOR_PROXIMITY, default=data.get(CONF_MIN_UPDATES_FOR_PROXIMITY, DEFAULT_MIN_UPDATES_FOR_PROXIMITY)): _num_slider(
                    1, 10, 1
                ),
                vol.Required(CONF_UPDATE_WINDOW_S, default=data.get(CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S)): _num_box(
                    60, 1800, 30, "s"
                ),
                vol.Required(CONF_REQUIRE_RELIABLE_PROXIMITY, default=data.get(CONF_REQUIRE_RELIABLE_PROXIMITY, DEFAULT_REQUIRE_RELIABLE_PROXIMITY)): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)