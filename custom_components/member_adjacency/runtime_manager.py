"""Runtime-safe adjacency manager.

This module keeps the public behavior of :mod:`manager` while ensuring that
movement and reliability counters are updated only for the source entity that
actually changed. It also separates raw distance hysteresis from the reliable
proximity state exposed to automations.

The reliability gate decides when proximity starts. Once proximity is on, only
the exit threshold ends it, so a source that goes quiet while two people stay
together does not produce a leave/enter pair. The proximity state saved by the
binary sensor is restored before the first calculation, so a restart or an
options reload does not replay enter events.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Collection
from datetime import datetime
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import restore_state
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
    DOMAIN,
    EVENT_ENTER,
    EVENT_ENTER_UNRELIABLE,
    EVENT_LEAVE,
    EVENT_PROXIMITY_UPDATE,
)
from .manager import AdjacencyManager as BaseAdjacencyManager
from .manager import _bucket, _get

# Re-check a held side this long after its resync hold ends, so the wall clock
# is past the hold even when the timer fires slightly early.
HOLD_END_MARGIN_S = 1.0


def _parse_utc(value: Any) -> datetime | None:
    """Parse a saved timezone-aware ISO timestamp."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


class AdjacencyManager(BaseAdjacencyManager):
    """Track proximity using source-aware movement and reliability samples."""

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry)
        self._pending_changed_sides: set[str] = set()
        self._refresh_lock = asyncio.Lock()
        self._raw_proximity = False
        self._refresh_tasks: set[asyncio.Task] = set()
        self._hold_end_timers: dict[str, Callable[[], None]] = {}
        self._stopped = False

    async def async_start(self) -> None:
        """Continue the saved state, calculate once and follow both sources."""
        self.async_restore_state()
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

    async def async_stop(self) -> None:
        """Cancel debounce, listeners and any in-flight refresh before unload.

        A stopped manager ignores refreshes that were already on their way,
        such as a refresh-button press that is still waiting for the phone.
        """
        self._stopped = True
        await super().async_stop()
        self._pending_changed_sides.clear()
        timers = list(self._hold_end_timers.values())
        self._hold_end_timers.clear()
        for cancel in timers:
            cancel()
        tasks = list(self._refresh_tasks)
        self._refresh_tasks.clear()
        for task in tasks:
            task.cancel()

    # --- saved state ---
    def _stored_state(self, entity_id: str):
        """Saved state of an entity from Home Assistant's restore data."""
        data = restore_state.async_get(self.hass)
        get_stored_state = getattr(data, "async_get_stored_state", None)
        if callable(get_stored_state):
            # Newer Home Assistant versions index saved states by entity
            # registry entry and expose this lookup instead of last_states.
            return get_stored_state(entity_id)
        return data.last_states.get(entity_id)

    def restore_snapshot(self) -> dict[str, Any]:
        """Proximity state the binary sensor saves for the next start."""
        return {
            "proximity": bool(self.data.proximity),
            "raw_proximity": bool(self._raw_proximity),
            "proximity_update_count": int(self.data.proximity_update_count),
            "proximity_since": (
                self._proximity_since.isoformat() if self._proximity_since else None
            ),
            "last_changed": self.data.last_changed,
            "last_entered": self.data.last_entered,
            "last_left": self.data.last_left,
        }

    @callback
    def async_restore_state(self) -> None:
        """Seed proximity from the state Home Assistant saved for this entry.

        Nothing is restored on a first install, after upgrading from a version
        that did not save the state, while the proximity binary sensor is
        disabled, or when the saved data is malformed.
        """
        try:
            registry = er.async_get(self.hass)
            entity_id = registry.async_get_entity_id(
                "binary_sensor", DOMAIN, f"{self.entry.entry_id}_proximity"
            )
            if not entity_id:
                return
            if getattr(registry.async_get(entity_id), "disabled", False):
                # A disabled sensor stops saving: its saved state is stale.
                return
            stored = self._stored_state(entity_id)
        except (AttributeError, KeyError):
            return
        extra = getattr(stored, "extra_data", None)
        saved = extra.as_dict() if extra is not None else None
        if not isinstance(saved, dict) or not isinstance(saved.get("proximity"), bool):
            return

        proximity = saved["proximity"]
        raw_proximity = proximity or saved.get("raw_proximity") is True
        count = saved.get("proximity_update_count")
        if not proximity:
            count = 0
        elif isinstance(count, bool) or not isinstance(count, int) or count < 1:
            count = 1

        self.data.proximity = proximity
        self._raw_proximity = raw_proximity
        setattr(self.data, "raw_proximity", raw_proximity)
        self.data.proximity_update_count = count
        for key in ("last_changed", "last_entered", "last_left"):
            value = saved.get(key)
            if isinstance(value, str):
                setattr(self.data, key, value)
        self._proximity_since = (
            _parse_utc(saved.get("proximity_since")) if proximity else None
        )

    # --- refresh scheduling ---
    def _schedule_refresh(
        self,
        changed_sides: set[str] | None = None,
        *,
        force_both: bool = False,
    ) -> None:
        """Create a tracked refresh task so unload can cancel it cleanly."""
        if self._stopped:
            return
        if force_both:
            coro = self.async_refresh(force_both=True)
        else:
            coro = self.async_refresh(changed_sides=changed_sides)
        task = self.hass.async_create_task(coro)
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

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
        if self._stopped:
            return
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
            self._schedule_refresh(changed)
            return

        @callback
        def _later(_now) -> None:
            self._cancel_debounce = None
            changed = self._consume_changed_sides()
            self._schedule_refresh(changed)

        self._cancel_debounce = async_call_later(self.hass, self.debounce_s, _later)

    async def async_force_refresh(self) -> None:
        """Recalculate now; a source update still in debounce is processed as one."""
        if self._cancel_debounce:
            self._cancel_debounce()
            self._cancel_debounce = None
        pending = set(self._pending_changed_sides)
        self._pending_changed_sides.clear()
        if pending:
            await self.async_refresh(changed_sides=pending)
        else:
            await self.async_refresh(force_both=True)

    def _schedule_hold_end_refresh(self, side: str) -> None:
        """Re-check once the resync hold of ``side`` is over."""
        if self._stopped:
            return
        until = self.a_resync_until if side == "a" else self.b_resync_until
        if until is None:
            return
        cancel = self._hold_end_timers.pop(side, None)
        if cancel is not None:
            cancel()
        delay = (
            max(0.0, (until - dt_util.utcnow()).total_seconds()) + HOLD_END_MARGIN_S
        )

        @callback
        def _hold_ended(_now) -> None:
            self._hold_end_timers.pop(side, None)
            self._schedule_refresh(force_both=True)

        self._hold_end_timers[side] = async_call_later(self.hass, delay, _hold_ended)

    # --- calculation ---
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

    def _held_sides(self) -> list[str]:
        """Sides that are still inside their resync hold window."""
        now = dt_util.utcnow()
        return [
            side
            for side, until in (("a", self.a_resync_until), ("b", self.b_resync_until))
            if until is not None and now < until
        ]

    def _hold_sample(self, sides: Collection[str]) -> None:
        """Keep the current state until the resync hold of ``sides`` is over."""
        ordered = sorted(sides)
        self.data.last_error = f"resync_{ordered[0]}"
        for side in ordered:
            self._schedule_hold_end_refresh(side)
        async_dispatcher_send(self.hass, self.signal)

    async def async_refresh(
        self,
        *,
        changed_sides: Collection[str] | None = None,
        force_both: bool = False,
    ) -> None:
        """Recompute state using only genuine source updates for movement history.

        A forced refresh (startup, refresh button, end of a resync hold) uses
        the current coordinates of both sides but is not a location update:
        it is not counted for reliability, does not move the last fix and
        does not fire ``proximity_update``. While either side is inside its
        resync hold the state is kept, whatever triggered the refresh.
        """
        if self._stopped:
            return
        forced = force_both or changed_sides is None
        effective_changed = (
            {"a", "b"}
            if forced
            else {side for side in changed_sides if side in {"a", "b"}}
        )
        if not effective_changed:
            return

        async with self._refresh_lock:
            if self._stopped:
                return
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

            previous_fix = {"a": self.a_last_fix, "b": self.b_last_fix}
            movement_error = super()._update_movement(
                coords_a if "a" in effective_changed else None,
                coords_b if "b" in effective_changed else None,
                initialize_only=forced,
            )
            if movement_error is not None:
                if movement_error.startswith("resync_"):
                    self._hold_sample([movement_error.rsplit("_", 1)[-1]])
                else:
                    self._mark_invalid(movement_error)
                return

            held = self._held_sides()
            if held:
                # The held side's coordinates are its suspect fix: do not
                # decide proximity on them before the hold ends. A genuine
                # update of the other side still counts.
                if not forced:
                    for side in sorted(effective_changed - set(held)):
                        self._record_update(side)
                self._hold_sample(held)
                return

            if not forced:
                for side in sorted(effective_changed):
                    self._record_update(side)

            lat1, lon1 = coords_a
            lat2, lon2 = coords_b
            distance = ha_distance(lat1, lon1, lat2, lon2)
            if distance is None:
                self._mark_invalid("distance_unavailable")
                return
            meters_raw = float(distance)

            # The distance change covers each moved side's travel since its
            # previous fix, not only the time since the last calculation.
            moved_since = [
                previous_fix[side]
                for side in effective_changed
                if not forced
                and previous_fix[side] is not None
                and not self._is_static_side(side)
            ]
            reliable, unreliable_reason = self._check_proximity_reliability(
                meters_raw,
                convergence_since=min(moved_since) if moved_since else None,
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
            gate_open = reliable or not self.require_reliable_proximity
            # Reliability decides when proximity starts; once it is on, only
            # the exit threshold ends it.
            proximity = (
                raw_proximity if previous_proximity else raw_proximity and gate_open
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
            elif proximity and gate_open and not forced:
                # Unreliable samples and recalculations keep proximity on but
                # are not reported as proximity updates.
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
