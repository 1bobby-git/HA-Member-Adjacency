"""Runtime-safe adjacency manager.

This module keeps the public behavior of :mod:`manager` while ensuring that
movement and reliability counters are updated only for the source entity that
actually changed. It also separates raw distance hysteresis from the reliable
proximity state exposed to automations.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance

from .const import (
    CONF_DEBOUNCE_SECONDS,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_FORCE_METERS,
    CONF_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH,
    CONF_MIN_UPDATES_FOR_PROXIMITY,
    CONF_REQUIRE_RELIABLE_PROXIMITY,
    CONF_RESYNC_HOLD_S,
    CONF_RESYNC_SILENCE_S,
    CONF_UPDATE_WINDOW_S,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_FORCE_METERS,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_MAX_SPEED_KMH,
    DEFAULT_MIN_UPDATES_FOR_PROXIMITY,
    DEFAULT_REQUIRE_RELIABLE_PROXIMITY,
    DEFAULT_RESYNC_HOLD_S,
    DEFAULT_RESYNC_SILENCE_S,
    DEFAULT_UPDATE_WINDOW_S,
    EVENT_ENTER,
    EVENT_ENTER_UNRELIABLE,
    EVENT_LEAVE,
    EVENT_PROXIMITY_UPDATE,
)
from .manager import AdjacencyManager as BaseAdjacencyManager
from .manager import _bucket, _get


class AdjacencyManager(BaseAdjacencyManager):
    """Track proximity using source-aware movement and reliability samples."""

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry)
        self._pending_changed_sides: set[str] = set()
        self._refresh_lock = asyncio.Lock()
        self._raw_proximity = False

    async def async_start(self) -> None:
        """Perform the initial calculation and subscribe to both source states."""
        await self.async_refresh(force_both=True)

        @callback
        def _handle(event) -> None:
            data = getattr(event, "data", None)
            entity_id = data.get("entity_id") if isinstance(data, dict) else None
            self.request_refresh(entity_id)

        self._unsub = async_track_state_change_event(
            self.hass,
            [self.entity_a, self.entity_b],
            _handle,
        )

    def _side_for_entity(self, entity_id: str | None) -> str | None:
        if entity_id == self.entity_a:
            return "a"
        if entity_id == self.entity_b:
            return "b"
        return None

    def _consume_changed_sides(self) -> set[str]:
        changed = set(self._pending_changed_sides)
        self._pending_changed_sides.clear()
        return changed or {"a", "b"}

    def request_refresh(self, changed_entity_id: str | None = None) -> None:
        """Coalesce source updates without fabricating an update for the other side."""
        side = self._side_for_entity(changed_entity_id)
        if side is None:
            self._pending_changed_sides.update(("a", "b"))
        else:
            self._pending_changed_sides.add(side)

        if self._cancel_debounce:
            self._cancel_debounce()
            self._cancel_debounce = None

        if self.debounce_s <= 0:
            changed = self._consume_changed_sides()
            self.hass.async_create_task(self.async_refresh(changed_sides=changed))
            return

        @callback
        def _later(_now) -> None:
            self._cancel_debounce = None
            changed = self._consume_changed_sides()
            self.hass.async_create_task(self.async_refresh(changed_sides=changed))

        self._cancel_debounce = async_call_later(self.hass, self.debounce_s, _later)

    async def async_force_refresh(self) -> None:
        """Recalculate both sources after cancelling any pending debounce."""
        if self._cancel_debounce:
            self._cancel_debounce()
            self._cancel_debounce = None
        self._pending_changed_sides.clear()
        await self.async_refresh(force_both=True)

    def _event_data(
        self,
        meters_raw: float,
        reliable: bool,
        unreliable_reason: str | None,
        update_count: int,
    ) -> dict[str, Any]:
        convergence = self.data.convergence_speed_kmh
        return {
            "base_entity": self.base_entity,
            "tracker_entity": self.tracker_entity,
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "distance_m": int(round(meters_raw)),
            "entry_threshold_m": self.entry_th,
            "exit_threshold_m": self.exit_th,
            "proximity_update_count": update_count,
            "proximity_reliable": reliable,
            "unreliable_reason": unreliable_reason,
            "base_updates_in_window": self.data.a_updates_in_window,
            "tracker_updates_in_window": self.data.b_updates_in_window,
            "a_updates_in_window": self.data.a_updates_in_window,
            "b_updates_in_window": self.data.b_updates_in_window,
            "convergence_speed_kmh": (
                None if convergence is None else round(convergence, 1)
            ),
        }

    def _mark_invalid(self, reason: str) -> None:
        self.data.data_valid = False
        self.data.last_error = reason
        async_dispatcher_send(self.hass, self.signal)

    async def async_refresh(
        self,
        *,
        changed_sides: Collection[str] | None = None,
        force_both: bool = False,
    ) -> None:
        """Recompute state using only genuine source updates for movement history."""
        effective_changed = (
            {"a", "b"}
            if force_both or changed_sides is None
            else {side for side in changed_sides if side in {"a", "b"}}
        )
        if not effective_changed:
            return

        async with self._refresh_lock:
            self.entry_th = int(
                _get(self.entry, CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)
            )
            self.exit_th = int(
                _get(self.entry, CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)
            )
            self.debounce_s = int(
                _get(self.entry, CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)
            )
            self.max_acc_m = int(
                _get(self.entry, CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M)
            )
            self.force_meters = bool(
                _get(self.entry, CONF_FORCE_METERS, DEFAULT_FORCE_METERS)
            )
            self.resync_silence_s = int(
                _get(self.entry, CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S)
            )
            self.resync_hold_s = int(
                _get(self.entry, CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S)
            )
            self.max_speed_kmh = float(
                _get(self.entry, CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH)
            )
            self.min_updates_for_proximity = int(
                _get(
                    self.entry,
                    CONF_MIN_UPDATES_FOR_PROXIMITY,
                    DEFAULT_MIN_UPDATES_FOR_PROXIMITY,
                )
            )
            self.update_window_s = int(
                _get(self.entry, CONF_UPDATE_WINDOW_S, DEFAULT_UPDATE_WINDOW_S)
            )
            self.require_reliable_proximity = bool(
                _get(
                    self.entry,
                    CONF_REQUIRE_RELIABLE_PROXIMITY,
                    DEFAULT_REQUIRE_RELIABLE_PROXIMITY,
                )
            )

            coords_a, acc_a = self._coords_and_acc(self.entity_a)
            coords_b, acc_b = self._coords_and_acc(self.entity_b)
            self.data.accuracy_a = acc_a
            self.data.accuracy_b = acc_b

            if coords_a is None or coords_b is None:
                self._mark_invalid("missing_coords")
                return

            if self.max_acc_m > 0:
                if acc_a is not None and acc_a > float(self.max_acc_m):
                    self._mark_invalid("accuracy_filtered_a")
                    return
                if acc_b is not None and acc_b > float(self.max_acc_m):
                    self._mark_invalid("accuracy_filtered_b")
                    return

            movement_error = super()._update_movement(
                coords_a if "a" in effective_changed else None,
                coords_b if "b" in effective_changed else None,
            )
            if movement_error is not None:
                self._mark_invalid(movement_error)
                return

            for side in sorted(effective_changed):
                self._record_update(side)

            lat1, lon1 = coords_a
            lat2, lon2 = coords_b
            meters_raw = float(ha_distance(lat1, lon1, lat2, lon2))

            reliable, unreliable_reason = self._check_proximity_reliability(
                meters_raw
            )
            self.data.proximity_reliable = reliable
            self.data.unreliable_reason = unreliable_reason

            now = dt_util.utcnow()
            self._prev_distance_m = meters_raw
            self._prev_distance_time = now
            self.data.distance_m = meters_raw
            self.data.bucket = _bucket(meters_raw)
            self.data.data_valid = True
            self.data.last_error = None
            self.data.last_valid_updated = now.isoformat()

            previous_raw = self._raw_proximity
            previous_proximity = self.data.proximity
            raw_proximity = (
                meters_raw < float(self.exit_th)
                if previous_raw
                else meters_raw <= float(self.entry_th)
            )
            proximity = raw_proximity and (
                reliable or not self.require_reliable_proximity
            )
            self._raw_proximity = raw_proximity
            setattr(self.data, "raw_proximity", raw_proximity)

            if raw_proximity and not previous_raw and not proximity:
                self.hass.bus.async_fire(
                    EVENT_ENTER_UNRELIABLE,
                    self._event_data(
                        meters_raw,
                        reliable,
                        unreliable_reason,
                        0,
                    ),
                )

            if proximity != previous_proximity:
                now_iso = now.isoformat()
                self.data.last_changed = now_iso
                if proximity:
                    self.data.proximity_update_count = 1
                    self.data.last_entered = now_iso
                    self._proximity_since = now
                    event_data = self._event_data(
                        meters_raw,
                        reliable,
                        unreliable_reason,
                        1,
                    )
                    self.hass.bus.async_fire(EVENT_ENTER, event_data)
                    self.hass.bus.async_fire(
                        EVENT_PROXIMITY_UPDATE,
                        {
                            **event_data,
                            "is_first_update": True,
                        },
                    )
                else:
                    self.data.proximity_update_count = 0
                    self.data.last_left = now_iso
                    self._proximity_since = None
                    self.hass.bus.async_fire(
                        EVENT_LEAVE,
                        self._event_data(
                            meters_raw,
                            reliable,
                            unreliable_reason,
                            0,
                        ),
                    )
            elif proximity:
                self.data.proximity_update_count += 1
                event_data = self._event_data(
                    meters_raw,
                    reliable,
                    unreliable_reason,
                    self.data.proximity_update_count,
                )
                self.hass.bus.async_fire(
                    EVENT_PROXIMITY_UPDATE,
                    {
                        **event_data,
                        "is_first_update": False,
                    },
                )

            if not proximity:
                self._proximity_since = None
            elif self._proximity_since is None:
                self._proximity_since = now

            self.data.proximity = proximity
            async_dispatcher_send(self.hass, self.signal)
