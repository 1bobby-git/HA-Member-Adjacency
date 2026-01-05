from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util.location import distance as ha_distance
from homeassistant.util import dt as dt_util

from .const import (
    BUCKETS,
    CONF_DEBOUNCE_SECONDS,
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_FORCE_METERS,
    CONF_MAX_ACCURACY_M,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_FORCE_METERS,
    DEFAULT_MAX_ACCURACY_M,
    DOMAIN,
    EVENT_ENTER,
    EVENT_LEAVE,
    SIGNAL_UPDATE_PREFIX,
)


@dataclass
class AdjacencyData:
    distance_m: float | None = None
    bucket: str | None = None
    proximity: bool = False
    last_changed: str | None = None
    last_entered: str | None = None
    last_left: str | None = None


def _get(entry: ConfigEntry, key: str, default: Any) -> Any:
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def _obj_id(entity_id: str) -> str:
    return entity_id.split(".", 1)[1]


def _short(entity_id: str) -> str:
    return _obj_id(entity_id).replace("_geocoded_location", "")


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


def _bucket(distance_m: float) -> str:
    for limit, name in BUCKETS:
        if distance_m < limit:
            return name
    return BUCKETS[-1][1]


class AdjacencyManager:
    """Compute adjacency once and share across entities (sensor/binary_sensor/button)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.entity_a: str = _get(entry, CONF_ENTITY_A, "")
        self.entity_b: str = _get(entry, CONF_ENTITY_B, "")

        self.entry_th: int = int(_get(entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th: int = int(_get(entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.debounce_s: int = int(_get(entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS))
        self.max_acc_m: int = int(_get(entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters: bool = bool(_get(entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))

        self.data = AdjacencyData()

        self._unsub = None
        self._cancel_debounce = None

    @property
    def pair_key(self) -> str:
        a_id = _short(self.entity_a) if self.entity_a else "a"
        b_id = _short(self.entity_b) if self.entity_b else "b"
        return f"{a_id}_{b_id}"

    @property
    def signal(self) -> str:
        return f"{SIGNAL_UPDATE_PREFIX}_{self.entry.entry_id}"

    def device_name(self) -> str:
        return f"인접센서 { _short(self.entity_a) }↔{ _short(self.entity_b) }"

    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": self.device_name(),
            "manufacturer": "1bobby-git",
            "model": "Member Adjacency Distance",
        }

    async def async_start(self) -> None:
        await self.async_refresh()

        @callback
        def _handle(_event) -> None:
            self.request_refresh()

        self._unsub = async_track_state_change_event(
            self.hass, [self.entity_a, self.entity_b], _handle
        )

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._cancel_debounce:
            self._cancel_debounce()
            self._cancel_debounce = None

    def request_refresh(self) -> None:
        """Debounced refresh."""
        if self._cancel_debounce:
            self._cancel_debounce()
            self._cancel_debounce = None

        if self.debounce_s <= 0:
            self.hass.async_create_task(self.async_refresh())
            return

        @callback
        def _later(_now) -> None:
            self._cancel_debounce = None
            self.hass.async_create_task(self.async_refresh())

        self._cancel_debounce = async_call_later(self.hass, self.debounce_s, _later)

    async def async_force_refresh(self) -> None:
        """Immediate refresh (button)."""
        if self._cancel_debounce:
            self._cancel_debounce()
            self._cancel_debounce = None
        await self.async_refresh()

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

    async def async_refresh(self) -> None:
        # refresh options dynamically
        self.entry_th = int(_get(self.entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th = int(_get(self.entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.debounce_s = int(_get(self.entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS))
        self.max_acc_m = int(_get(self.entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters = bool(_get(self.entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))

        prev_prox = self.data.proximity

        a = self._coords_if_ok(self.entity_a)
        b = self._coords_if_ok(self.entity_b)

        if a is None or b is None:
            # distance unknown; keep proximity to reduce flapping
            self.data.distance_m = None
            self.data.bucket = None
            async_dispatcher_send(self.hass, self.signal)
            return

        lat1, lon1 = a
        lat2, lon2 = b

        meters = float(ha_distance(lat1, lon1, lat2, lon2))  # returns meters
        self.data.distance_m = meters
        self.data.bucket = _bucket(meters)

        # hysteresis
        if prev_prox:
            prox = meters < float(self.exit_th)
        else:
            prox = meters <= float(self.entry_th)

        if prox != prev_prox:
            now = dt_util.utcnow().isoformat()
            self.data.last_changed = now
            if prox:
                self.data.last_entered = now
                self.hass.bus.async_fire(
                    EVENT_ENTER,
                    {
                        "entity_a": self.entity_a,
                        "entity_b": self.entity_b,
                        "distance_m": int(round(meters)),
                        "entry_threshold_m": self.entry_th,
                        "exit_threshold_m": self.exit_th,
                    },
                )
            else:
                self.data.last_left = now
                self.hass.bus.async_fire(
                    EVENT_LEAVE,
                    {
                        "entity_a": self.entity_a,
                        "entity_b": self.entity_b,
                        "distance_m": int(round(meters)),
                        "entry_threshold_m": self.entry_th,
                        "exit_threshold_m": self.exit_th,
                    },
                )

        self.data.proximity = prox

        async_dispatcher_send(self.hass, self.signal)
