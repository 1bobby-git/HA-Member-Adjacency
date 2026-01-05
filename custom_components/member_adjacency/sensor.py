from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.location import distance as ha_distance

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


def _get_entry_value(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Prefer options over data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


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

    # If state is "lat,lon"
    if isinstance(state.state, str) and "," in state.state:
        parts = [p.strip() for p in state.state.split(",")]
        if len(parts) == 2:
            try:
                return (float(parts[0]), float(parts[1]))
            except (TypeError, ValueError):
                return None

    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    entity = MemberAdjacencyDistanceSensor(hass, entry)
    async_add_entities([entity])


@dataclass
class _DistanceData:
    native_value: int | float | None = None
    attrs: dict[str, Any] | None = None


class MemberAdjacencyDistanceSensor(SensorEntity):
    """Distance (meters) between two entities exposing coordinates."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry

        self._entity_a: str = _get_entry_value(entry, CONF_ENTITY_A)
        self._entity_b: str = _get_entry_value(entry, CONF_ENTITY_B)

        self._name: str = _get_entry_value(entry, CONF_NAME, DEFAULT_NAME)
        self._icon: str = _get_entry_value(entry, CONF_ICON, DEFAULT_ICON)
        self._rounding: int = _get_entry_value(entry, CONF_ROUNDING, DEFAULT_ROUNDING)
        self._threshold_m: int = _get_entry_value(
            entry, CONF_PROXIMITY_THRESHOLD_M, DEFAULT_PROXIMITY_THRESHOLD_M
        )

        self._attr_name = self._name
        self._attr_icon = self._icon
        self._attr_unique_id = entry.entry_id

        self._data = _DistanceData(native_value=None, attrs={})

    @property
    def native_value(self) -> int | float | None:
        return self._data.native_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._data.attrs or {}

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._name,
            "manufacturer": "Custom",
            "model": "Adjacency Distance",
        }

    async def async_added_to_hass(self) -> None:
        await self._async_recompute()

        @callback
        def _handle_event(event) -> None:
            # schedule async update
            self.hass.async_create_task(self._async_recompute_and_write())

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._entity_a, self._entity_b], _handle_event
            )
        )

    async def _async_recompute_and_write(self) -> None:
        await self._async_recompute()
        self.async_write_ha_state()

    async def _async_recompute(self) -> None:
        # refresh possibly changed options/entities
        self._entity_a = _get_entry_value(self._entry, CONF_ENTITY_A)
        self._entity_b = _get_entry_value(self._entry, CONF_ENTITY_B)
        self._name = _get_entry_value(self._entry, CONF_NAME, DEFAULT_NAME)
        self._icon = _get_entry_value(self._entry, CONF_ICON, DEFAULT_ICON)
        self._rounding = _get_entry_value(self._entry, CONF_ROUNDING, DEFAULT_ROUNDING)
        self._threshold_m = _get_entry_value(
            self._entry, CONF_PROXIMITY_THRESHOLD_M, DEFAULT_PROXIMITY_THRESHOLD_M
        )

        self._attr_name = self._name
        self._attr_icon = self._icon

        st_a = self.hass.states.get(self._entity_a)
        st_b = self.hass.states.get(self._entity_b)

        coords_a = _try_get_coords_from_state(st_a)
        coords_b = _try_get_coords_from_state(st_b)

        attrs: dict[str, Any] = {
            "entity_a": self._entity_a,
            "entity_b": self._entity_b,
            "proximity_threshold_m": self._threshold_m,
        }

        if coords_a is None or coords_b is None:
            attrs["error"] = "missing_coordinates"
            attrs["coords_a"] = coords_a
            attrs["coords_b"] = coords_b
            self._data = _DistanceData(native_value=None, attrs=attrs)
            return

        lat1, lon1 = coords_a
        lat2, lon2 = coords_b

        # HA util.location.distance returns kilometers
        km = ha_distance(lat1, lon1, lat2, lon2)
        meters = km * 1000.0

        if self._rounding == 0:
            native_val: int | float = int(round(meters))
        else:
            native_val = round(meters, self._rounding)

        attrs["coords_a"] = {"lat": lat1, "lon": lon1}
        attrs["coords_b"] = {"lat": lat2, "lon": lon2}
        attrs["distance_km"] = round(km, 6)
        attrs["proximity"] = bool(meters < float(self._threshold_m))

        self._data = _DistanceData(native_value=native_val, attrs=attrs)
