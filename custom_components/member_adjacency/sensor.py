from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.location import distance as ha_distance

from .const import (
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_PROXIMITY_THRESHOLD_M,
    DEFAULT_ICON,
    DEFAULT_NAME_KO,
    DEFAULT_PROXIMITY_THRESHOLD_M,
    DOMAIN,
)


def _get_entry_value(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    # ✅ 첫 생성 시 entity_id를 sensor.member_adjacency로 유도
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        entry.entry_id,  # entity unique_id (platform+domain+unique_id로 매칭)
        suggested_object_id="member_adjacency",
        config_entry=entry,
    )

    async_add_entities([MemberAdjacencyDistanceSensor(hass, entry)])


@dataclass
class _DistanceData:
    native_value: int | float | None = None
    attrs: dict[str, Any] | None = None
    native_unit: str | None = None


class MemberAdjacencyDistanceSensor(SensorEntity):
    """Distance between two geocoded entities with proximity attribute."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry

        self._entity_a: str = _get_entry_value(entry, CONF_ENTITY_A)
        self._entity_b: str = _get_entry_value(entry, CONF_ENTITY_B)
        self._threshold_m: int = _get_entry_value(
            entry, CONF_PROXIMITY_THRESHOLD_M, DEFAULT_PROXIMITY_THRESHOLD_M
        )

        self._attr_name = DEFAULT_NAME_KO
        self._attr_icon = DEFAULT_ICON  # ✅ mdi:cellphone
        self._attr_unique_id = entry.entry_id  # registry key

        self._data = _DistanceData(
            native_value=None, attrs={}, native_unit=UnitOfLength.METERS
        )

    @property
    def native_value(self) -> int | float | None:
        return self._data.native_value

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._data.native_unit

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._data.attrs or {}

    async def async_added_to_hass(self) -> None:
        await self._async_recompute()

        @callback
        def _handle_event(event) -> None:
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
        self._threshold_m = _get_entry_value(
            self._entry, CONF_PROXIMITY_THRESHOLD_M, DEFAULT_PROXIMITY_THRESHOLD_M
        )

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
            self._data = _DistanceData(
                native_value=None, attrs=attrs, native_unit=UnitOfLength.METERS
            )
            return

        lat1, lon1 = coords_a
        lat2, lon2 = coords_b

        # ha_distance는 "미터(m)" 반환
        meters = float(ha_distance(lat1, lon1, lat2, lon2))
        km = meters / 1000.0

        if meters >= 1000.0:
            native_unit = UnitOfLength.KILOMETERS
            native_val: int | float = round(km, 2)
        else:
            native_unit = UnitOfLength.METERS
            native_val = int(round(meters))

        attrs["coords_a"] = {"lat": lat1, "lon": lon1}
        attrs["coords_b"] = {"lat": lat2, "lon": lon2}
        attrs["distance_m"] = int(round(meters))
        attrs["distance_km"] = round(km, 3)
        attrs["proximity"] = bool(meters < float(self._threshold_m))

        self._data = _DistanceData(
            native_value=native_val, attrs=attrs, native_unit=native_unit
        )
