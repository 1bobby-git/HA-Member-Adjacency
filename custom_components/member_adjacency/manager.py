"""
Core computation for the Member Adjacency component.

The :class:`AdjacencyManager` encapsulates all of the logic needed to
compute distances between two location-providing entities, apply
hysteresis for proximity entry/exit, filter out invalid readings and
expose calculated values through a lightweight data object.  It also
provides an interface for requesting location updates and firing events
on the Home Assistant bus when proximity changes occur.

This modified version adds support for filtering unrealistic movement
based on calculated speed and delayed location updates (resynchronisation).
Each side maintains its previous coordinates and timestamp of the last
update.  If a long period of silence is followed by a new update, the
update is considered a resync and ignored for a short period.  If the
computed speed between two updates exceeds a configurable maximum, the
update is treated as invalid.  These features help to prevent false
proximity notifications when GPS coordinates jump or arrive out of order.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceNotFound
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance  # HA Core distance (meters)

from .const import (
    BUCKETS,
    CONF_DEBOUNCE_SECONDS,
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_BASE_ENTITY,
    CONF_TRACKER_ENTITY,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_FORCE_METERS,
    CONF_MAX_ACCURACY_M,
    CONF_RESYNC_SILENCE_S,
    CONF_RESYNC_HOLD_S,
    CONF_MAX_SPEED_KMH,
    CONF_MIN_UPDATES_FOR_PROXIMITY,
    CONF_UPDATE_WINDOW_S,
    CONF_REQUIRE_RELIABLE_PROXIMITY,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_FORCE_METERS,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_RESYNC_SILENCE_S,
    DEFAULT_RESYNC_HOLD_S,
    DEFAULT_MAX_SPEED_KMH,
    DEFAULT_MIN_UPDATES_FOR_PROXIMITY,
    DEFAULT_UPDATE_WINDOW_S,
    DEFAULT_REQUIRE_RELIABLE_PROXIMITY,
    DOMAIN,
    EVENT_ENTER,
    EVENT_ENTER_UNRELIABLE,
    EVENT_LEAVE,
    EVENT_PROXIMITY_UPDATE,
    SIGNAL_UPDATE_PREFIX,
)


@dataclass
class AdjacencyData:
    """Structure holding the latest computed data for an adjacency."""

    # raw meters (NOT rounded, NOT scaled)
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

    # proximity zone 진입 후 위치 업데이트 횟수 (1 = 첫 진입, 2+ = 이후 업데이트)
    proximity_update_count: int = 0

    # 신뢰도 관련 속성
    proximity_reliable: bool = True  # 신뢰할 수 있는 근접인지
    unreliable_reason: str | None = None  # 신뢰 불가 사유
    a_updates_in_window: int = 0  # A의 최근 업데이트 횟수
    b_updates_in_window: int = 0  # B의 최근 업데이트 횟수
    convergence_speed_kmh: float | None = None  # 두 엔티티가 가까워지는 속도


def _get(entry: ConfigEntry, key: str, default: Any) -> Any:
    """Helper to read a value from config entry options first then data."""
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
    """Extract latitude/longitude from a state object."""
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
    """Extract a GPS accuracy value from a state object's attributes."""
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
    """Map a raw distance in meters to a named bucket."""
    for limit, name in BUCKETS:
        if distance_m < limit:
            return name
    return BUCKETS[-1][1]


def _sanitize_service_suffix(s: str) -> str:
    """Sanitize a service name suffix for the mobile_app integration."""
    return (
        s.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace(".", "_")
        .replace(":", "_")
    )


def _format_duration_ko(total_seconds: int) -> str:
    """Return a human-friendly duration string in Korean."""
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

        # Support both new (base/tracker) and legacy (entity_a/entity_b) config keys
        self.base_entity: str = _get(entry, CONF_BASE_ENTITY, "") or _get(entry, CONF_ENTITY_A, "")
        self.tracker_entity: str = _get(entry, CONF_TRACKER_ENTITY, "") or _get(entry, CONF_ENTITY_B, "")

        # Legacy aliases for internal compatibility
        self.entity_a = self.base_entity
        self.entity_b = self.tracker_entity

        # Hysteresis thresholds, debounce and accuracy filtering
        self.entry_th: int = int(_get(entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th: int = int(_get(entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.debounce_s: int = int(_get(entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS))
        self.max_acc_m: int = int(_get(entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters: bool = bool(_get(entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))

        # New options for movement filtering
        self.resync_silence_s: int = int(_get(entry, CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S))
        self.resync_hold_s: int = int(_get(entry, CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S))
        self.max_speed_kmh: float = float(_get(entry, CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH))
        self.min_updates_for_proximity: int = int(_get(entry, CONF_MIN_UPDATES_FOR_PROXIMITY, DEFAULT_MIN_UPDATES_FOR_PROXIMITY))
        self.update_window_s: int = int(_get(entry, CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S))
        self.require_reliable_proximity: bool = bool(_get(entry, CONF_REQUIRE_RELIABLE_PROXIMITY, DEFAULT_REQUIRE_RELIABLE_PROXIMITY))

        # Data container shared with entities
        self.data = AdjacencyData()

        # Unsubscription callbacks
        self._unsub = None
        self._cancel_debounce = None
        self._proximity_since: datetime | None = None

        # Per side movement tracking
        self.a_prev_coords: tuple[float, float] | None = None
        self.b_prev_coords: tuple[float, float] | None = None
        self.a_last_fix: datetime | None = None
        self.b_last_fix: datetime | None = None
        self.a_speed_kmh: float | None = None
        self.b_speed_kmh: float | None = None
        self.a_resync_until: datetime | None = None
        self.b_resync_until: datetime | None = None

        # 업데이트 이력 추적 (최근 업데이트 타임스탬프 리스트)
        self.a_update_history: list[datetime] = []
        self.b_update_history: list[datetime] = []

        # 이전 거리 (수렴 속도 계산용)
        self._prev_distance_m: float | None = None
        self._prev_distance_time: datetime | None = None

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

    def get_base_name(self) -> str:
        """Get friendly name for base entity (기준점)."""
        return self._resolve_device_name(self.base_entity)

    def get_tracker_name(self) -> str:
        """Get friendly name for tracker entity (추적 대상)."""
        return self._resolve_device_name(self.tracker_entity)

    def device_name(self) -> str:
        return f"{self.get_tracker_name()} → {self.get_base_name()}"

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

    # --- compute helpers ---
    def _coords_and_acc(self, entity_id: str) -> tuple[tuple[float, float] | None, float | None]:
        st = self.hass.states.get(entity_id)
        return _try_get_coords_from_state(st), _get_accuracy_m(st)

    def _count_recent_updates(self, history: list[datetime], window_s: int) -> int:
        """지정된 윈도우 내의 업데이트 횟수를 반환."""
        now = dt_util.utcnow()
        cutoff = now - timedelta(seconds=window_s)
        return sum(1 for ts in history if ts >= cutoff)

    def _prune_history(self, history: list[datetime], window_s: int) -> list[datetime]:
        """오래된 항목을 제거하고 윈도우 내의 항목만 유지."""
        now = dt_util.utcnow()
        cutoff = now - timedelta(seconds=window_s)
        return [ts for ts in history if ts >= cutoff]

    def _record_update(self, side: str) -> None:
        """업데이트 이력에 현재 시간 기록."""
        now = dt_util.utcnow()
        if side == "a":
            self.a_update_history.append(now)
            self.a_update_history = self._prune_history(self.a_update_history, self.update_window_s * 2)
        else:
            self.b_update_history.append(now)
            self.b_update_history = self._prune_history(self.b_update_history, self.update_window_s * 2)

    def _calculate_convergence_speed(self, current_distance_m: float) -> float | None:
        """두 엔티티가 가까워지는 속도(km/h) 계산. 양수 = 가까워짐, 음수 = 멀어짐."""
        if self._prev_distance_m is None or self._prev_distance_time is None:
            return None
        now = dt_util.utcnow()
        dt_seconds = (now - self._prev_distance_time).total_seconds()
        if dt_seconds <= 0:
            return None
        # 거리 변화 (양수 = 가까워짐)
        delta_m = self._prev_distance_m - current_distance_m
        # 속도 (km/h)
        speed_kmh = (delta_m / dt_seconds) * 3.6
        return speed_kmh

    def _check_proximity_reliability(self, current_distance_m: float) -> tuple[bool, str | None]:
        """
        근접 이벤트의 신뢰도를 확인.

        Returns:
            (reliable, reason) - reliable=False이면 reason에 사유 포함
        """
        # 1. 양쪽 업데이트 빈도 확인
        a_updates = self._count_recent_updates(self.a_update_history, self.update_window_s)
        b_updates = self._count_recent_updates(self.b_update_history, self.update_window_s)

        self.data.a_updates_in_window = a_updates
        self.data.b_updates_in_window = b_updates

        if a_updates < self.min_updates_for_proximity:
            return False, f"insufficient_updates_a ({a_updates}<{self.min_updates_for_proximity})"
        if b_updates < self.min_updates_for_proximity:
            return False, f"insufficient_updates_b ({b_updates}<{self.min_updates_for_proximity})"

        # 2. 수렴 속도 확인 (거리가 줄어드는 속도)
        convergence = self._calculate_convergence_speed(current_distance_m)
        self.data.convergence_speed_kmh = convergence

        if convergence is not None:
            # 두 객체가 서로 다가오는 최대 속도 = 양쪽 max_speed 합산
            max_convergence = self.max_speed_kmh * 2
            if convergence > max_convergence:
                return False, f"unrealistic_convergence ({convergence:.1f} > {max_convergence} km/h)"

        # 3. resync 상태 확인
        now = dt_util.utcnow()
        if self.a_resync_until and now < self.a_resync_until:
            return False, "resync_a"
        if self.b_resync_until and now < self.b_resync_until:
            return False, "resync_b"

        return True, None

    def _update_movement(self, coords_a: tuple[float, float] | None, coords_b: tuple[float, float] | None) -> str | None:
        """
        Update per-side movement and detect unrealistic movement or resync.

        Returns an error string if either side's update should be ignored due to
        resynchronisation or unrealistic speed.  When an error is returned the
        caller should treat the entire update as invalid and refrain from
        updating the distance or firing events.
        """
        now = dt_util.utcnow()

        def process_side(side: str, coords: tuple[float, float] | None) -> str | None:
            # Determine attribute names based on side
            if side == "a":
                prev_coords = self.a_prev_coords
                last_fix = self.a_last_fix
                resync_until = self.a_resync_until
            else:
                prev_coords = self.b_prev_coords
                last_fix = self.b_last_fix
                resync_until = self.b_resync_until

            # If no new coords we can't compute movement for this side
            if coords is None:
                return None

            # Silence detection: if last fix exists and a long period has elapsed, mark as resync
            if last_fix and (now - last_fix).total_seconds() > self.resync_silence_s:
                # Schedule resync hold window
                until = now + timedelta(seconds=self.resync_hold_s)
                if side == "a":
                    self.a_resync_until = until
                else:
                    self.b_resync_until = until
                # Reset speed and previous coords for this side
                if side == "a":
                    self.a_speed_kmh = None
                    self.a_prev_coords = coords
                    self.a_last_fix = now
                else:
                    self.b_speed_kmh = None
                    self.b_prev_coords = coords
                    self.b_last_fix = now
                return f"resync_{side}"

            # If currently within the resync hold window, skip this update
            if resync_until and now < resync_until:
                # Update prev coords and last_fix so that we don't compute huge speeds next time
                if side == "a":
                    self.a_prev_coords = coords
                    self.a_last_fix = now
                    self.a_speed_kmh = None
                else:
                    self.b_prev_coords = coords
                    self.b_last_fix = now
                    self.b_speed_kmh = None
                return f"resync_{side}"

            # If this is the first fix for the side just initialise state
            if prev_coords is None or last_fix is None:
                if side == "a":
                    self.a_prev_coords = coords
                    self.a_last_fix = now
                    self.a_speed_kmh = None
                else:
                    self.b_prev_coords = coords
                    self.b_last_fix = now
                    self.b_speed_kmh = None
                return None

            # Compute speed between previous fix and now
            dt_seconds = (now - last_fix).total_seconds()
            if dt_seconds <= 0:
                # Avoid division by zero
                if side == "a":
                    self.a_prev_coords = coords
                    self.a_last_fix = now
                    self.a_speed_kmh = None
                else:
                    self.b_prev_coords = coords
                    self.b_last_fix = now
                    self.b_speed_kmh = None
                return None

            # Distance in meters between previous and current coords
            dist_m = ha_distance(prev_coords[0], prev_coords[1], coords[0], coords[1])
            speed_kmh = (dist_m / dt_seconds) * 3.6

            # Update speed attribute
            if side == "a":
                self.a_speed_kmh = speed_kmh
            else:
                self.b_speed_kmh = speed_kmh

            # If max_speed_kmh > 0 and speed exceeds it, filter this update
            if self.max_speed_kmh > 0 and speed_kmh > self.max_speed_kmh:
                # Update prev/last fix anyway to avoid compounding next time
                if side == "a":
                    self.a_prev_coords = coords
                    self.a_last_fix = now
                else:
                    self.b_prev_coords = coords
                    self.b_last_fix = now
                return f"speed_filtered_{side}"

            # Update state for side
            if side == "a":
                self.a_prev_coords = coords
                self.a_last_fix = now
            else:
                self.b_prev_coords = coords
                self.b_last_fix = now
            return None

        # Process both sides
        for side, coords in (("a", coords_a), ("b", coords_b)):
            err = process_side(side, coords)
            if err:
                return err
        return None

    async def async_refresh(self) -> None:
        """Recompute distance and proximity state."""
        # dynamic options (may change via options flow)
        self.entry_th = int(_get(self.entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M))
        self.exit_th = int(_get(self.entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M))
        self.debounce_s = int(_get(self.entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS))
        self.max_acc_m = int(_get(self.entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M))
        self.force_meters = bool(_get(self.entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS))
        # dynamic new options
        self.resync_silence_s = int(_get(self.entry, CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S))
        self.resync_hold_s = int(_get(self.entry, CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S))
        self.max_speed_kmh = float(_get(self.entry, CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH))
        self.min_updates_for_proximity = int(_get(self.entry, CONF_MIN_UPDATES_FOR_PROXIMITY, DEFAULT_MIN_UPDATES_FOR_PROXIMITY))
        self.update_window_s = int(_get(self.entry, CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S))
        self.require_reliable_proximity = bool(_get(self.entry, CONF_REQUIRE_RELIABLE_PROXIMITY, DEFAULT_REQUIRE_RELIABLE_PROXIMITY))

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

        # movement filtering
        movement_err = self._update_movement(coords_a, coords_b)
        if movement_err is not None:
            # mark data invalid and annotate error
            self.data.data_valid = False
            self.data.last_error = movement_err
            async_dispatcher_send(self.hass, self.signal)
            return

        # 업데이트 이력 기록 (유효한 좌표일 때만)
        self._record_update("a")
        self._record_update("b")

        # Compute distance
        lat1, lon1 = coords_a
        lat2, lon2 = coords_b
        # HA Core distance() returns meters
        meters_raw = float(ha_distance(lat1, lon1, lat2, lon2))

        # 신뢰도 검사 (proximity 진입 시에만 적용)
        reliable, unreliable_reason = self._check_proximity_reliability(meters_raw)
        self.data.proximity_reliable = reliable
        self.data.unreliable_reason = unreliable_reason

        # 이전 거리 저장 (수렴 속도 계산용)
        self._prev_distance_m = meters_raw
        self._prev_distance_time = dt_util.utcnow()

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
                # proximity entered: reset update_count to 1
                self.data.proximity_update_count = 1
                self.data.last_entered = now_iso
                self._proximity_since = dt_util.utcnow()

                # Determine which event to fire based on reliability and config
                event_data = {
                    "entity_a": self.entity_a,
                    "entity_b": self.entity_b,
                    "distance_m": int(round(meters_raw)),
                    "entry_threshold_m": self.entry_th,
                    "exit_threshold_m": self.exit_th,
                    "proximity_update_count": 1,
                    # 신뢰도 정보 추가
                    "proximity_reliable": reliable,
                    "unreliable_reason": unreliable_reason,
                    "a_updates_in_window": self.data.a_updates_in_window,
                    "b_updates_in_window": self.data.b_updates_in_window,
                    "convergence_speed_kmh": round(self.data.convergence_speed_kmh, 1) if self.data.convergence_speed_kmh else None,
                }

                if self.require_reliable_proximity and not reliable:
                    # Unreliable proximity with enforcement: fire unreliable event only
                    self.hass.bus.async_fire(EVENT_ENTER_UNRELIABLE, event_data)
                else:
                    # Reliable proximity OR enforcement disabled: fire normal event
                    self.hass.bus.async_fire(EVENT_ENTER, event_data)
                    # first proximity update (only fire when enter event is fired)
                    self.hass.bus.async_fire(
                        EVENT_PROXIMITY_UPDATE,
                        {
                            "entity_a": self.entity_a,
                            "entity_b": self.entity_b,
                            "distance_m": int(round(meters_raw)),
                            "proximity_update_count": 1,
                            "is_first_update": True,
                            "proximity_reliable": reliable,
                            "unreliable_reason": unreliable_reason,
                        },
                    )
            else:
                # proximity left: reset update_count
                self.data.proximity_update_count = 0
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
        elif prox:
            # already in proximity: increment update count
            self.data.proximity_update_count += 1
            # Only fire proximity update if reliable OR enforcement is disabled
            if not self.require_reliable_proximity or reliable:
                self.hass.bus.async_fire(
                    EVENT_PROXIMITY_UPDATE,
                    {
                        "entity_a": self.entity_a,
                        "entity_b": self.entity_b,
                        "distance_m": int(round(meters_raw)),
                        "proximity_update_count": self.data.proximity_update_count,
                        "is_first_update": False,
                        "proximity_reliable": reliable,
                        "unreliable_reason": unreliable_reason,
                    },
                )

        if prox and self._proximity_since is None:
            self._proximity_since = dt_util.utcnow()
        if not prox:
            self._proximity_since = None

        self.data.proximity = prox
        async_dispatcher_send(self.hass, self.signal)