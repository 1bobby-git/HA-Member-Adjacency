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
from homeassistant.data_entry_flow import section

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
    """Try to extract coordinates from an entity state."""
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
    """Get the device name for an entity."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    ent = ent_reg.async_get(entity_id)
    if ent and ent.device_id:
        dev = dev_reg.async_get(ent.device_id)
        if dev:
            return dev.name_by_user or dev.name
    return None


def _friendly_or_entity(hass: HomeAssistant, entity_id: str) -> str:
    """Get friendly name or entity_id."""
    st = hass.states.get(entity_id)
    if st and (st.attributes or {}).get("friendly_name"):
        return str(st.attributes["friendly_name"])
    return entity_id


def _label_for_entity(hass: HomeAssistant, entity_id: str) -> str:
    """Create a descriptive label for an entity (device name or friendly name only)."""
    dev_name = _device_name_for_entity(hass, entity_id)
    if dev_name:
        return dev_name
    fn = _friendly_or_entity(hass, entity_id)
    if fn != entity_id:
        return fn
    # Fallback: extract readable name from entity_id
    obj_id = entity_id.split(".", 1)[1] if "." in entity_id else entity_id
    # Remove common suffixes for cleaner display
    for suffix in ("_geocoded_location", "_location", "_gps"):
        if obj_id.endswith(suffix):
            obj_id = obj_id[:-len(suffix)]
            break
    return obj_id.replace("_", " ").title()


def _group_name(entity_id: str) -> str:
    """Determine the group name for sorting."""
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
    """Return sort order for groups."""
    order = {
        "Geocoded": 0,
        "Device Tracker": 1,
        "Person": 2,
        "Zone": 3,
        "Sensor": 4,
        "Other": 9,
    }
    return order.get(group, 9)


def _candidate_entities_grouped(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """
    Return a list of selectable location entities grouped and sorted for display.

    - Only entities with coordinates are included.
    - Geocoded sensors are prioritized at the top.
    - Sorted by group and then by a friendly label.
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
        base_label = _label_for_entity(hass, eid)
        label = f"{g} · {base_label}"
        rows.append((_group_order(g), base_label, label, eid))

    rows.sort(key=lambda x: (x[0], x[1]))
    return [
        selector.SelectOptionDict(value=eid, label=label)
        for _, _, label, eid in rows
    ]


class MemberAdjacencyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Member Adjacency."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        # Get grouped entity options
        options = _candidate_entities_grouped(self.hass)

        if user_input is not None:
            a = user_input.get(CONF_BASE_ENTITY)
            b = user_input.get(CONF_TRACKER_ENTITY)

            # Extract advanced settings from nested section
            advanced = user_input.get("advanced_settings", {})

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
                    # Advanced settings from section
                    CONF_RESYNC_SILENCE_S: advanced.get(CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S),
                    CONF_RESYNC_HOLD_S: advanced.get(CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S),
                    CONF_MAX_SPEED_KMH: advanced.get(CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH),
                    CONF_MIN_UPDATES_FOR_PROXIMITY: advanced.get(CONF_MIN_UPDATES_FOR_PROXIMITY, DEFAULT_MIN_UPDATES_FOR_PROXIMITY),
                    CONF_UPDATE_WINDOW_S: advanced.get(CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S),
                    CONF_REQUIRE_RELIABLE_PROXIMITY: advanced.get(CONF_REQUIRE_RELIABLE_PROXIMITY, DEFAULT_REQUIRE_RELIABLE_PROXIMITY),
                }

                return self.async_create_entry(title=title, data=data_to_store)

        # Entity selector with grouped options and custom value allowed
        entity_sel = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
                sort=False,
            )
        )

        # Advanced settings schema (will be in collapsible section)
        advanced_schema = vol.Schema({
            vol.Required(CONF_RESYNC_SILENCE_S, default=DEFAULT_RESYNC_SILENCE_S): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=86400, step=60, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_RESYNC_HOLD_S, default=DEFAULT_RESYNC_HOLD_S): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=600, step=5, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_MAX_SPEED_KMH, default=DEFAULT_MAX_SPEED_KMH): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1000, step=10, unit_of_measurement="km/h", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_MIN_UPDATES_FOR_PROXIMITY, default=DEFAULT_MIN_UPDATES_FOR_PROXIMITY): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=10, step=1, mode=selector.NumberSelectorMode.SLIDER)
            ),
            vol.Required(CONF_UPDATE_WINDOW_S, default=DEFAULT_UPDATE_WINDOW_S): selector.NumberSelector(
                selector.NumberSelectorConfig(min=60, max=1800, step=30, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_REQUIRE_RELIABLE_PROXIMITY, default=DEFAULT_REQUIRE_RELIABLE_PROXIMITY): selector.BooleanSelector(),
        })

        # Main schema with basic settings and collapsible advanced section
        schema = vol.Schema({
            vol.Required(CONF_BASE_ENTITY): entity_sel,
            vol.Required(CONF_TRACKER_ENTITY): entity_sel,
            vol.Required(CONF_ENTRY_THRESHOLD_M, default=DEFAULT_ENTRY_THRESHOLD_M): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1000000, step=10, unit_of_measurement="m", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_EXIT_THRESHOLD_M, default=DEFAULT_EXIT_THRESHOLD_M): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1000000, step=10, unit_of_measurement="m", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_DEBOUNCE_SECONDS, default=DEFAULT_DEBOUNCE_SECONDS): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=60, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.SLIDER)
            ),
            vol.Required(CONF_MAX_ACCURACY_M, default=DEFAULT_MAX_ACCURACY_M): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=10000, step=10, unit_of_measurement="m", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_FORCE_METERS, default=DEFAULT_FORCE_METERS): selector.BooleanSelector(),
            # Advanced settings in collapsible section (collapsed by default)
            vol.Required("advanced_settings"): section(
                advanced_schema,
                {"collapsed": True}
            ),
        })

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
            # Extract advanced settings from nested section
            advanced = user_input.get("advanced_settings", {})

            entry_th = int(user_input.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
            exit_th = int(user_input.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"

            if not errors:
                # Flatten the data for storage
                flat_data = {
                    CONF_ENTRY_THRESHOLD_M: user_input.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M),
                    CONF_EXIT_THRESHOLD_M: user_input.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M),
                    CONF_DEBOUNCE_SECONDS: user_input.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS),
                    CONF_MAX_ACCURACY_M: user_input.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M),
                    CONF_FORCE_METERS: user_input.get(CONF_FORCE_METERS, DEFAULT_FORCE_METERS),
                    CONF_RESYNC_SILENCE_S: advanced.get(CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S),
                    CONF_RESYNC_HOLD_S: advanced.get(CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S),
                    CONF_MAX_SPEED_KMH: advanced.get(CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH),
                    CONF_MIN_UPDATES_FOR_PROXIMITY: advanced.get(CONF_MIN_UPDATES_FOR_PROXIMITY, DEFAULT_MIN_UPDATES_FOR_PROXIMITY),
                    CONF_UPDATE_WINDOW_S: advanced.get(CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S),
                    CONF_REQUIRE_RELIABLE_PROXIMITY: advanced.get(CONF_REQUIRE_RELIABLE_PROXIMITY, DEFAULT_REQUIRE_RELIABLE_PROXIMITY),
                }
                return self.async_create_entry(title="", data=flat_data)

        # Advanced settings schema
        advanced_schema = vol.Schema({
            vol.Required(CONF_RESYNC_SILENCE_S, default=data.get(CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=86400, step=60, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_RESYNC_HOLD_S, default=data.get(CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=600, step=5, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_MAX_SPEED_KMH, default=data.get(CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1000, step=10, unit_of_measurement="km/h", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_MIN_UPDATES_FOR_PROXIMITY, default=data.get(CONF_MIN_UPDATES_FOR_PROXIMITY, DEFAULT_MIN_UPDATES_FOR_PROXIMITY)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=10, step=1, mode=selector.NumberSelectorMode.SLIDER)
            ),
            vol.Required(CONF_UPDATE_WINDOW_S, default=data.get(CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=60, max=1800, step=30, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_REQUIRE_RELIABLE_PROXIMITY, default=data.get(CONF_REQUIRE_RELIABLE_PROXIMITY, DEFAULT_REQUIRE_RELIABLE_PROXIMITY)): selector.BooleanSelector(),
        })

        # Main options schema
        schema = vol.Schema({
            vol.Required(CONF_ENTRY_THRESHOLD_M, default=data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1000000, step=10, unit_of_measurement="m", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_EXIT_THRESHOLD_M, default=data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1000000, step=10, unit_of_measurement="m", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_DEBOUNCE_SECONDS, default=data.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=60, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.SLIDER)
            ),
            vol.Required(CONF_MAX_ACCURACY_M, default=data.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=10000, step=10, unit_of_measurement="m", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_FORCE_METERS, default=data.get(CONF_FORCE_METERS, DEFAULT_FORCE_METERS)): selector.BooleanSelector(),
            vol.Required("advanced_settings"): section(
                advanced_schema,
                {"collapsed": True}
            ),
        })

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
