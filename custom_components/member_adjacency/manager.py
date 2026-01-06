from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceNotFound
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance  # ✅ HA Core distance (meters)
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
    # ✅ raw meters (NOT rounded, NOT scaled)
    distance_m: float | None = None
    bucket: str | None = None
    proximity: bool = False

    data_valid: bool = False
    last_valid_updated: str | None = None
    last_error: str | None = None

    last_changed: str | None = None
    last_entered: str | None = None
    last_left: str | None = None

    accuracy_a: float | None = None
    accuracy_b: float | None = None


def _get(entry: ConfigEntry, key: str, default: Any) -> Any:
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def _obj_id(entity_id: str) -> str:
    return entity_id.split(".", 1)[1]


def _short(entity_id: str) -> str:
    return _obj_id(entity_id).replace("_geocoded_location", "")


def _round1(x: float) -> float:
    return round(float(x), 1)


def _try_get_coords_from_state(state) -> tuple[float, float] | None:
    if state is None:
        return None

    attrs = state.attributes or {}

    # mobile_app geocoded sensor
    loc = attrs.get("Location")
    if isinstance(loc, (list, tuple)) and len(loc) == 2:
        try:
            return (float(loc[0]), float(loc[1]))
        except (TypeError, ValueError):
            return None

    # general entities
    if "latitude" in attrs and "longitude" in attrs:
        try:
            return (float(attrs["latitude"]), float(attrs["longitude"]))
        except (TypeError, ValueError):
            return None

    # string state "lat,lon"
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


def _sanitize_service_suffix(s: str) -> str:
    return (
        s.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace(".", "_")
        .replace(":", "_")
    )


def _format_duration_ko(total_seconds: int) -> str:
    if total_seconds <= 0:
        return "0분"
    total_minutes = int(round(total_seconds / 60))
    if total_minutes <= 0:
        return "0분"

    days = total_minutes // (24 * 60)
    rem = total_minutes % (24 * 60)
    hours = rem // 60
    minutes = rem % 60

    parts: list[str] = []
    if days:
        parts.append(f"{days}일")
    if hours:
        parts.append(f"{hours}시간")
    if minutes:
        parts.append(f"{minutes}분")
    return " ".join(parts) if parts else "0분"


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
        self._proximity_since: datetime | None = None

    @property
    def pair_key(self) -> str:
        a_id = _short(self.entity_a) if self.entity_a else "a"
        b_id = _short(self.entity_b) if self.entity_b else "b"
        return f"{a_id}_{b_id}"

    @property
    def signal(self) -> str:
        return f"{SIGNAL_UPDATE_PREFIX}_{self.entry.entry_id}"

    # --- device naming ---
    def _fallback_name(self, entity_id: str) -> str:
        st = self.hass.states.get(entity_id)
        if st and (st.attributes or {}).get("friendly_name"):
            return str(st.attributes["friendly_name"])
        return _short(entity_id) if entity_id else entity_id

    def _resolve_device_name(self, entity_id: str) -> str:
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)

        ent = ent_reg.async_get(entity_id)
        if ent and ent.device_id:
            dev = dev_reg.async_get(ent.device_id)
            if dev:
                return dev.name_by_user or dev.name or self._fallback_name(entity_id)
        return self._fallback_name(entity_id)

    def device_name(self) -> str:
        return f"{self._resolve_device_name(self.entity_a)} ↔ {self._resolve_device_name(self.entity_b)}"

    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": self.device_name(),
            "manufacturer": "1bobby-git",
            "model": "Member Adjacency Distance",
        }

    # --- proximity duration ---
    def proximity_duration_seconds(self) -> int:
        if not self.data.proximity or self._proximity_since is None:
            return 0
        delta = dt_util.utcnow() - self._proximity_since
        return max(0, int(delta.total_seconds()))

    def proximity_duration_minutes(self) -> float:
        return _round1(self.proximity_duration_seconds() / 60.0)

    def proximity_duration_human(self) -> str:
        return _format_duration_ko(self.proximity_duration_seconds())

    # --- lifecycle ---
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

    # --- refresh button: try source update then refresh ---
    def _mobile_app_identifier_from_entity(self, entity_id: str) -> str | None:
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)

        ent = ent_reg.async_get(entity_id)
        if not ent or not ent.device_id:
            return None

        dev = dev_reg.async_get(ent.device_id)
        if not dev:
            return None

        for ident in dev.identifiers:
            try:
                domain, dev_id = ident
            except ValueError:
                continue
            if domain == "mobile_app":
                return str(dev_id)
        return None

    async def async_request_source_update(self, entity_id: str) -> None:
        if not entity_id or entity_id.startswith("zone."):
            return

        mobile_id = self._mobile_app_identifier_from_entity(entity_id)
        if mobile_id:
            service = f"mobile_app_{_sanitize_service_suffix(mobile_id)}"
            if self.hass.services.has_service("notify", service):
                try:
                    await self.hass.services.async_call(
                        "notify",
                        service,
                        {"message": "request_location_update"},
                        blocking=True,
                    )
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

        if self.hass.services.has_service("homeassistant", "update_entity"):
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "update_entity",
                    {"entity_id": entity_id},
                    blocking=True,
                )
            except (ServiceNotFound, Exception):
                pass

    async def async_force_refresh_with_source_update(self) -> None:
        await self.async_request_source_update(self.entity_a)
        await self.async_request_source_update(self.entity_b)
        await self.async_force_refresh()

    async def async_force_refresh(self) -> None:
        if self._cancel_debounce:
            self._cancel_debounce()
            self._cancel_debounce = None
        await self.async_refresh()

    # --- compute ---
    def _coords_and_acc(self, entity_id: str) -> tuple[tuple[float, float] | None, float | None]:
        st = self.hass.states.get(entity_id)
        return _try_get_coords_from_state(st), _get_accuracy_m(st)

    async def async_refresh(self) -> None:
        # dynamic options
        self.entry_th = int(_get(self.entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th = int(_get(self.entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.debounce_s = int(_get(self.entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS))
        self.max_acc_m = int(_get(self.entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters = bool(_get(self.entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))

        prev_prox = self.data.proximity

        coords_a, acc_a = self._coords_and_acc(self.entity_a)
        coords_b, acc_b = self._coords_and_acc(self.entity_b)
        self.data.accuracy_a = acc_a
        self.data.accuracy_b = acc_b

        # invalid coords => keep last good, mark invalid
        if coords_a is None or coords_b is None:
            self.data.data_valid = False
            self.data.last_error = "missing_coords"
            async_dispatcher_send(self.hass, self.signal)
            return

        # accuracy filter
        if self.max_acc_m > 0:
            if acc_a is not None and acc_a > float(self.max_acc_m):
                self.data.data_valid = False
                self.data.last_error = "accuracy_filtered_a"
                async_dispatcher_send(self.hass, self.signal)
                return
            if acc_b is not None and acc_b > float(self.max_acc_m):
                self.data.data_valid = False
                self.data.last_error = "accuracy_filtered_b"
                async_dispatcher_send(self.hass, self.signal)
                return

        lat1, lon1 = coords_a
        lat2, lon2 = coords_b

        # ✅ 핵심: HA Core distance()는 "meters" 반환
        meters_raw = float(ha_distance(lat1, lon1, lat2, lon2))

        self.data.distance_m = meters_raw
        self.data.bucket = _bucket(meters_raw)
        self.data.data_valid = True
        self.data.last_error = None
        self.data.last_valid_updated = dt_util.utcnow().isoformat()

        # hysteresis uses raw meters
        if prev_prox:
            prox = meters_raw < float(self.exit_th)
        else:
            prox = meters_raw <= float(self.entry_th)

        if prox != prev_prox:
            now_iso = dt_util.utcnow().isoformat()
            self.data.last_changed = now_iso

            if prox:
                self.data.last_entered = now_iso
                self._proximity_since = dt_util.utcnow()
                self.hass.bus.async_fire(
                    EVENT_ENTER,
                    {
                        "entity_a": self.entity_a,
                        "entity_b": self.entity_b,
                        "distance_m": int(round(meters_raw)),
                        "entry_threshold_m": self.entry_th,
                        "exit_threshold_m": self.exit_th,
                    },
                )
            else:
                self.data.last_left = now_iso
                self._proximity_since = None
                self.hass.bus.async_fire(
                    EVENT_LEAVE,
                    {
                        "entity_a": self.entity_a,
                        "entity_b": self.entity_b,
                        "distance_m": int(round(meters_raw)),
                        "entry_threshold_m": self.entry_th,
                        "exit_threshold_m": self.exit_th,
                    },
                )

        if prox and self._proximity_since is None:
            self._proximity_since = dt_util.utcnow()
        if not prox:
            self._proximity_since = None

        self.data.proximity = prox
        async_dispatcher_send(self.hass, self.signal)
