from __future__ import annotations

import math
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.util.location import distance as ha_distance
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
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
    DEFAULT_NAME_KO,
    BUCKETS,
    EVENT_ENTER,
    EVENT_LEAVE,
)


def _get(entry: ConfigEntry, key: str, default: Any) -> Any:
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def _obj_id(entity_id: str) -> str:
    return entity_id.split(".", 1)[1]


def _short(entity_id: str) -> str:
    # 센서명에 너무 길게 붙지 않도록 suffix 제거
    oid = _obj_id(entity_id)
    return oid.replace("_geocoded_location", "")


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


def _get_accuracy_m(state) -> float | None:
    if state is None:
        return None
    attrs = state.attributes or {}
    for k in ("gps_accuracy", "accuracy", "horizontal_accuracy"):
        v = attrs.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    brng = math.degrees(math.atan2(y, x))
    return int((brng + 360) % 360)


def _bucket(distance_m: float) -> str:
    for limit, name in BUCKETS:
        if distance_m < limit:
            return name
    return BUCKETS[-1][1]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    a = _get(entry, CONF_ENTITY_A, "")
    b = _get(entry, CONF_ENTITY_B, "")

    # 엔티티 ID 충돌을 피하기 위해 pair 기반 object_id 사용
    a_id = _short(a)
    b_id = _short(b)
    pair_key = f"{a_id}_{b_id}" if a_id and b_id else entry.entry_id

    ent_reg = er.async_get(hass)

    # distance (primary)
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_distance",
        suggested_object_id=f"member_adjacency_{pair_key}",
        config_entry=entry,
    )
    # bearing
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_bearing",
        suggested_object_id=f"member_adjacency_{pair_key}_bearing",
        config_entry=entry,
    )
    # bucket
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_bucket",
        suggested_object_id=f"member_adjacency_{pair_key}_bucket",
        config_entry=entry,
    )

    async_add_entities([
        MemberAdjacencyDistanceSensor(hass, entry),
        MemberAdjacencyBearingSensor(hass, entry),
        MemberAdjacencyBucketSensor(hass, entry),
    ])


class _BaseAdjacencySensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.entity_a = _get(entry, CONF_ENTITY_A, "")
        self.entity_b = _get(entry, CONF_ENTITY_B, "")

        self.entry_th = int(_get(entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th = int(_get(entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.debounce_s = int(_get(entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS))
        self.max_acc_m = int(_get(entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters = bool(_get(entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))

        # shared computed
        self._distance_m: float | None = None
        self._bearing: int | None = None
        self._bucket: str | None = None

        self._proximity: bool = False
        self._last_changed: str | None = None
        self._last_entered: str | None = None
        self._last_left: str | None = None

        self._cancel_debounce = None

    async def async_added_to_hass(self) -> None:
        await self._async_recompute()

        @callback
        def _handle(_event) -> None:
            self._schedule_recompute()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.entity_a, self.entity_b], _handle
            )
        )

    def _schedule_recompute(self) -> None:
        if self._cancel_debounce is not None:
            self._cancel_debounce()
            self._cancel_debounce = None

        if self.debounce_s <= 0:
            self.hass.async_create_task(self._async_recompute_and_write())
            return

        @callback
        def _later(_now) -> None:
            self._cancel_debounce = None
            self.hass.async_create_task(self._async_recompute_and_write())

        self._cancel_debounce = async_call_later(self.hass, self.debounce_s, _later)

    def _coords_if_ok(self, entity_id: str) -> tuple[float, float] | None:
        st = self.hass.states.get(entity_id)
        coords = _try_get_coords_from_state(st)
        if coords is None:
            return None

        if self.max_acc_m > 0:
            acc = _get_accuracy_m(st)
            if acc is not None and acc > float(self.max_acc_m):
                return None

        return coords

    async def _async_recompute_and_write(self) -> None:
        await self._async_recompute()
        self.async_write_ha_state()

    async def _async_recompute(self) -> None:
        # options refresh
        self.entry_th = int(_get(self.entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th = int(_get(self.entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.debounce_s = int(_get(self.entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS))
        self.max_acc_m = int(_get(self.entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters = bool(_get(self.entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))

        a = self._coords_if_ok(self.entity_a)
        b = self._coords_if_ok(self.entity_b)

        prev_prox = self._proximity

        if a is None or b is None:
            # keep previous proximity to avoid flapping
            self._distance_m = None
            self._bearing = None
            self._bucket = None
            return

        lat1, lon1 = a
        lat2, lon2 = b

        meters = float(ha_distance(lat1, lon1, lat2, lon2))  # returns meters
        self._distance_m = meters
        self._bearing = _bearing_deg(lat1, lon1, lat2, lon2)
        self._bucket = _bucket(meters)

        # hysteresis
        if prev_prox:
            prox = meters < float(self.exit_th)
        else:
            prox = meters <= float(self.entry_th)

        if prox != prev_prox:
            now = dt_util.utcnow().isoformat()
            self._last_changed = now
            if prox:
                self._last_entered = now
                self.hass.bus.async_fire(EVENT_ENTER, {
                    "entity_a": self.entity_a,
                    "entity_b": self.entity_b,
                    "distance_m": int(round(meters)),
                    "entry_threshold_m": self.entry_th,
                    "exit_threshold_m": self.exit_th,
                })
            else:
                self._last_left = now
                self.hass.bus.async_fire(EVENT_LEAVE, {
                    "entity_a": self.entity_a,
                    "entity_b": self.entity_b,
                    "distance_m": int(round(meters)),
                    "entry_threshold_m": self.entry_th,
                    "exit_threshold_m": self.exit_th,
                })

        self._proximity = prox

    def _common_attrs(self) -> dict[str, Any]:
        d = self._distance_m
        return {
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "entry_threshold_m": self.entry_th,
            "exit_threshold_m": self.exit_th,
            "debounce_seconds": self.debounce_s,
            "max_accuracy_m": self.max_acc_m,
            "force_meters": self.force_meters,
            "distance_m": None if d is None else int(round(d)),
            "distance_km": None if d is None else round(d / 1000.0, 3),
            "bearing_deg": self._bearing,
            "bucket": self._bucket,
            "proximity": self._proximity,
            "last_changed": self._last_changed,
            "last_entered": self._last_entered,
            "last_left": self._last_left,
        }


class MemberAdjacencyDistanceSensor(_BaseAdjacencySensor):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_distance"
        self._attr_name = f"{DEFAULT_NAME_KO} {_short(self.entity_a)}↔{_short(self.entity_b)} 거리"

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.force_meters:
            return UnitOfLength.METERS
        if self._distance_m is not None and self._distance_m >= 1000:
            return UnitOfLength.KILOMETERS
        return UnitOfLength.METERS

    @property
    def native_value(self) -> int | float | None:
        d = self._distance_m
        if d is None:
            return None
        if self.force_meters:
            return int(round(d))
        if d >= 1000:
            return round(d / 1000.0, 2)
        return int(round(d))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()


class MemberAdjacencyBearingSensor(_BaseAdjacencySensor):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_bearing"
        self._attr_name = f"{DEFAULT_NAME_KO} {_short(self.entity_a)}→{_short(self.entity_b)} 방위각"
        self._attr_native_unit_of_measurement = "°"

    @property
    def native_value(self) -> int | None:
        return self._bearing

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()


class MemberAdjacencyBucketSensor(_BaseAdjacencySensor):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_bucket"
        self._attr_name = f"{DEFAULT_NAME_KO} {_short(self.entity_a)}↔{_short(self.entity_b)} 구간"

    @property
    def native_value(self) -> str | None:
        return self._bucket

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()
