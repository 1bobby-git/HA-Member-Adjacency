from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from homeassistant.util.location import distance as ha_distance
from homeassistant.util import dt as dt_util

from .const import (
    BUCKETS,
    CONF_ANCHOR,
    CONF_TARGETS,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_SECONDS,
    CONF_MAX_ACCURACY_M,
    CONF_FORCE_METERS,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_FORCE_METERS,
    DOMAIN,
    EVENT_ANY_ENTER,
    EVENT_ANY_LEAVE,
    EVENT_ENTER,
    EVENT_LEAVE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PairData:
    target: str
    distance_m: float | None
    bearing_deg: int | None
    bucket: str | None
    proximity: bool
    last_changed: str | None
    last_entered: str | None
    last_left: str | None


@dataclass
class SummaryData:
    anchor: str
    targets: list[str]
    nearest_target: str | None
    nearest_distance_m: float | None
    any_proximity: bool
    pairs: dict[str, PairData]
    force_meters: bool


def _get_entry_value(entry: ConfigEntry, key: str, default: Any) -> Any:
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


def _get_accuracy_m(state) -> float | None:
    if state is None:
        return None
    attrs = state.attributes or {}
    for k in ("gps_accuracy", "accuracy", "horizontal_accuracy"):
        v = attrs.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    # initial bearing (forward azimuth)
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


class MemberAdjacencyCoordinator(DataUpdateCoordinator[SummaryData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.anchor: str = _get_entry_value(entry, CONF_ANCHOR, "")
        self.targets: list[str] = list(_get_entry_value(entry, CONF_TARGETS, []))

        self.entry_th: int = int(_get_entry_value(entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th: int = int(_get_entry_value(entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.max_accuracy_m: int = int(_get_entry_value(entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters: bool = bool(_get_entry_value(entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))

        debounce_s = int(_get_entry_value(entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS))

        self._unsub = None
        self._pair_prev: dict[str, PairData] = {}
        self._any_prev: bool = False

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_method=self._async_update_data,
            debouncer=Debouncer(hass, _LOGGER, cooldown=debounce_s, immediate=True),
        )

    async def async_start(self) -> None:
        # track state changes for anchor + targets
        watch = [self.anchor] + list(self.targets)

        @callback
        def _handle(_event) -> None:
            self.async_request_refresh()

        self._unsub = async_track_state_change_event(self.hass, watch, _handle)
        await self.async_config_entry_first_refresh()

    async def async_shutdown(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    def _coords_if_ok(self, entity_id: str) -> tuple[float, float] | None:
        st = self.hass.states.get(entity_id)
        coords = _try_get_coords_from_state(st)
        if coords is None:
            return None

        if self.max_accuracy_m > 0:
            acc = _get_accuracy_m(st)
            if acc is not None and acc > float(self.max_accuracy_m):
                return None

        return coords

    async def _async_update_data(self) -> SummaryData:
        # refresh option values (in case options changed)
        self.entry_th = int(_get_entry_value(self.entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th = int(_get_entry_value(self.entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.max_accuracy_m = int(_get_entry_value(self.entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters = bool(_get_entry_value(self.entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))

        anchor_coords = self._coords_if_ok(self.anchor)

        pairs: dict[str, PairData] = {}
        nearest_target = None
        nearest_dist = None
        any_prox = False

        now_iso = dt_util.utcnow().isoformat()

        for t in self.targets:
            prev = self._pair_prev.get(t)
            prev_prox = prev.proximity if prev else False
            last_changed = prev.last_changed if prev else None
            last_entered = prev.last_entered if prev else None
            last_left = prev.last_left if prev else None

            coords_t = self._coords_if_ok(t)

            if anchor_coords is None or coords_t is None:
                dist_m = None
                bearing = None
                buck = None
                prox = prev_prox  # keep last known (reduces flapping to false on missing)
            else:
                lat1, lon1 = anchor_coords
                lat2, lon2 = coords_t

                # ha_distance returns METERS (do not multiply)
                dist_m = float(ha_distance(lat1, lon1, lat2, lon2))  # :contentReference[oaicite:1]{index=1}
                bearing = _bearing_deg(lat1, lon1, lat2, lon2)
                buck = _bucket(dist_m)

                # hysteresis:
                # - if currently false: become true when <= entry_th
                # - if currently true : become false when >= exit_th
                if prev_prox:
                    prox = dist_m < float(self.exit_th)
                else:
                    prox = dist_m <= float(self.entry_th)

            if dist_m is not None:
                if nearest_dist is None or dist_m < nearest_dist:
                    nearest_dist = dist_m
                    nearest_target = t

            any_prox = any_prox or prox

            # state change bookkeeping + events
            if prox != prev_prox:
                last_changed = now_iso
                payload = {
                    "anchor": self.anchor,
                    "target": t,
                    "distance_m": None if dist_m is None else int(round(dist_m)),
                    "entry_threshold_m": self.entry_th,
                    "exit_threshold_m": self.exit_th,
                }
                if prox:
                    last_entered = now_iso
                    self.hass.bus.async_fire(EVENT_ENTER, payload)
                else:
                    last_left = now_iso
                    self.hass.bus.async_fire(EVENT_LEAVE, payload)

            pairs[t] = PairData(
                target=t,
                distance_m=dist_m,
                bearing_deg=bearing,
                bucket=buck,
                proximity=prox,
                last_changed=last_changed,
                last_entered=last_entered,
                last_left=last_left,
            )

        # any_proximity events
        if any_prox != self._any_prev:
            payload = {
                "anchor": self.anchor,
                "any_proximity": any_prox,
                "entry_threshold_m": self.entry_th,
                "exit_threshold_m": self.exit_th,
                "nearest_target": nearest_target,
                "nearest_distance_m": None if nearest_dist is None else int(round(nearest_dist)),
            }
            if any_prox:
                self.hass.bus.async_fire(EVENT_ANY_ENTER, payload)
            else:
                self.hass.bus.async_fire(EVENT_ANY_LEAVE, payload)

        self._pair_prev = pairs
        self._any_prev = any_prox

        return SummaryData(
            anchor=self.anchor,
            targets=list(self.targets),
            nearest_target=nearest_target,
            nearest_distance_m=nearest_dist,
            any_proximity=any_prox,
            pairs=pairs,
            force_meters=self.force_meters,
        )


async def async_create_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> MemberAdjacencyCoordinator:
    coord = MemberAdjacencyCoordinator(hass, entry)
    await coord.async_start()
    return coord
