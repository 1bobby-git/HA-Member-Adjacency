"""Regression tests for the 1.6.8 proximity stability fixes."""

from __future__ import annotations

import ast
import asyncio
import importlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tests.test_manager import FakeEntry, FakeHass


def _install_platform_stubs() -> None:
    """Minimal entity platform modules so sensor/binary_sensor can be imported."""
    homeassistant = sys.modules["homeassistant"]
    components = types.ModuleType("homeassistant.components")
    binary_sensor = types.ModuleType("homeassistant.components.binary_sensor")
    sensor = types.ModuleType("homeassistant.components.sensor")
    const = types.ModuleType("homeassistant.const")

    class Entity:
        hass = None

        def async_on_remove(self, func) -> None:
            self.__dict__.setdefault("removers", []).append(func)

        def async_write_ha_state(self) -> None:
            self.__dict__["writes"] = self.__dict__.get("writes", 0) + 1

    class BinarySensorEntity(Entity):
        pass

    class SensorEntity(Entity):
        pass

    class SensorDeviceClass:
        DISTANCE = "distance"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    class UnitOfLength:
        METERS = "m"

    binary_sensor.BinarySensorEntity = BinarySensorEntity
    sensor.SensorEntity = SensorEntity
    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorStateClass = SensorStateClass
    const.UnitOfLength = UnitOfLength
    components.binary_sensor = binary_sensor
    components.sensor = sensor
    homeassistant.components = components
    homeassistant.const = const
    sys.modules.update(
        {
            "homeassistant.components": components,
            "homeassistant.components.binary_sensor": binary_sensor,
            "homeassistant.components.sensor": sensor,
            "homeassistant.const": const,
        }
    )


_install_platform_stubs()

package = importlib.import_module("custom_components.member_adjacency")
manager_module = importlib.import_module("custom_components.member_adjacency.manager")
runtime_module = importlib.import_module(
    "custom_components.member_adjacency.runtime_manager"
)
binary_sensor_module = importlib.import_module(
    "custom_components.member_adjacency.binary_sensor"
)
sensor_module = importlib.import_module("custom_components.member_adjacency.sensor")

COMPONENT_ROOT = (
    Path(__file__).resolve().parents[1] / "custom_components" / "member_adjacency"
)
START = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
BASE = (37.500000, 127.000000)
NEAR = (37.500900, 127.000000)  # about 100 m from BASE
FAR = (37.513500, 127.000000)  # about 1.5 km from BASE
PROXIMITY_ENTITY_ID = "binary_sensor.member_adjacency_base_tracker_proximity"
ENTER = runtime_module.EVENT_ENTER
ENTER_UNRELIABLE = runtime_module.EVENT_ENTER_UNRELIABLE
LEAVE = runtime_module.EVENT_LEAVE
UPDATE = runtime_module.EVENT_PROXIMITY_UPDATE


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def at(self, seconds: float) -> None:
        self.now = START + timedelta(seconds=seconds)


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))

    def names(self) -> list[str]:
        return [name for name, _data in self.events]


class Timers:
    """Record async_call_later calls instead of scheduling them."""

    def __init__(self) -> None:
        self.calls: list[types.SimpleNamespace] = []

    def __call__(self, _hass, delay, action):
        handle = types.SimpleNamespace(delay=delay, action=action, cancelled=False)
        self.calls.append(handle)

        def _cancel() -> None:
            handle.cancelled = True

        return _cancel


class _Case(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self._patch(runtime_module.dt_util, "utcnow", self.clock)
        self.timers = Timers()
        self._patch(runtime_module, "async_call_later", self.timers)
        self.positions: dict[str, tuple[float, float] | None] = {}

    def _patch(self, target, name: str, value) -> None:
        patcher = patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_manager(
        self,
        *,
        base: str = "person.base",
        tracker: str = "person.tracker",
        **options,
    ):
        data = {
            "base_entity": base,
            "tracker_entity": tracker,
            "entry_threshold_m": 500,
            "exit_threshold_m": 700,
            "debounce_seconds": 0,
            "max_speed_kmh": 0,
            "min_updates_for_proximity": 1,
            "require_reliable_proximity": True,
        }
        data.update(options)
        hass = FakeHass()
        hass.bus = RecordingBus()
        manager = runtime_module.AdjacencyManager(hass, FakeEntry(data=data))
        self.positions.update({base: BASE, tracker: NEAR})
        manager._coords_and_acc = lambda entity_id: (  # type: ignore[method-assign]
            self.positions.get(entity_id),
            5.0,
        )
        return manager

    async def update(self, manager, seconds: float, *sides: str) -> None:
        """A genuine location update of ``sides`` at START + seconds."""
        self.clock.at(seconds)
        await manager.async_refresh(changed_sides=set(sides))

    async def run_scheduled(self, manager) -> None:
        tasks = list(manager._refresh_tasks)
        if tasks:
            await asyncio.gather(*tasks)

    def saved_state(
        self,
        data: dict,
        *,
        registry_indexed: bool = False,
        disabled: bool = False,
    ) -> None:
        """Make Home Assistant's restore data hold ``data`` for this entry."""
        registry_entry = types.SimpleNamespace(disabled=disabled)
        registry = types.SimpleNamespace(
            async_get=lambda entity_id: (
                registry_entry if entity_id == PROXIMITY_ENTITY_ID else None
            ),
            async_get_entity_id=lambda domain, platform, unique_id: (
                PROXIMITY_ENTITY_ID
                if (domain, platform, unique_id)
                == ("binary_sensor", "member_adjacency", "entry-test_proximity")
                else None
            ),
        )
        stored = types.SimpleNamespace(
            # The saved data must work even when the entity was unavailable.
            state=types.SimpleNamespace(state="unavailable", attributes={}),
            extra_data=types.SimpleNamespace(as_dict=lambda: dict(data)),
        )
        if registry_indexed:
            # Newer Home Assistant: no last_states, lookup through a method.
            restore_data = types.SimpleNamespace(
                async_get_stored_state=lambda entity_id: (
                    stored if entity_id == PROXIMITY_ENTITY_ID else None
                )
            )
        else:
            restore_data = types.SimpleNamespace(
                last_states={PROXIMITY_ENTITY_ID: stored}
            )
        self._patch(runtime_module.er, "async_get", lambda _hass: registry)
        self._patch(
            runtime_module.restore_state, "async_get", lambda _hass: restore_data
        )


class StableProximityTests(_Case):
    """F1: once on, only the exit threshold ends proximity."""

    async def enter_together(self, manager) -> None:
        await self.update(manager, 0, "a", "b")
        await self.update(manager, 10, "a", "b")
        self.assertTrue(manager.data.proximity)
        manager.hass.bus.events.clear()

    async def test_quiet_source_does_not_end_proximity(self) -> None:
        manager = self.make_manager(min_updates_for_proximity=2)
        await self.enter_together(manager)

        await self.update(manager, 320, "b")  # base sent nothing for 310 s

        self.assertFalse(manager.data.proximity_reliable)
        self.assertTrue(manager.data.proximity)
        self.assertEqual([], manager.hass.bus.names())

        self.positions["person.tracker"] = FAR
        await self.update(manager, 330, "b")

        self.assertFalse(manager.data.proximity)
        self.assertEqual([LEAVE], manager.hass.bus.names())

    async def test_unreliable_sample_while_on_is_not_a_proximity_update(self) -> None:
        manager = self.make_manager(min_updates_for_proximity=2)
        await self.enter_together(manager)

        await self.update(manager, 320, "b")
        await self.update(manager, 330, "a")

        self.assertEqual([], manager.hass.bus.names())
        self.assertEqual(1, manager.data.proximity_update_count)

        await self.update(manager, 340, "a", "b")

        self.assertEqual([UPDATE], manager.hass.bus.names())
        data = manager.hass.bus.events[0][1]
        self.assertEqual(2, data["proximity_update_count"])
        self.assertFalse(data["is_first_update"])
        self.assertTrue(data["proximity_reliable"])

    async def test_updates_still_fire_when_reliability_is_not_required(self) -> None:
        manager = self.make_manager(
            min_updates_for_proximity=2, require_reliable_proximity=False
        )
        await self.update(manager, 0, "a", "b")
        manager.hass.bus.events.clear()

        await self.update(manager, 320, "b")

        self.assertEqual([UPDATE], manager.hass.bus.names())
        self.assertFalse(manager.hass.bus.events[0][1]["proximity_reliable"])


class ZoneTests(_Case):
    """F2: a zone is a fixed place."""

    async def test_zone_pair_enters_on_tracker_updates_alone(self) -> None:
        manager = self.make_manager(base="zone.home", min_updates_for_proximity=3)

        for seconds in (0, 30, 60):
            await self.update(manager, seconds, "b")

        self.assertTrue(manager.data.proximity)
        self.assertEqual([ENTER_UNRELIABLE, ENTER, UPDATE], manager.hass.bus.names())

    async def test_zone_change_after_long_quiet_is_not_a_resync(self) -> None:
        manager = self.make_manager(base="zone.home")
        await self.update(manager, 0, "a", "b")

        await self.update(manager, 1200, "a")  # someone arrived at home

        self.assertIsNone(manager.a_resync_until)
        self.assertIsNone(manager.data.last_error)
        self.assertTrue(manager.data.data_valid)
        self.assertIsNone(manager.a_speed_kmh)

    async def test_forced_refresh_does_not_move_known_fixes(self) -> None:
        manager = self.make_manager(base="zone.home")
        await self.update(manager, 0, "a", "b")

        self.clock.at(120)
        await manager.async_force_refresh()

        self.assertEqual(START, manager.a_last_fix)
        self.assertEqual(START, manager.b_last_fix)


class ResyncHoldTests(_Case):
    """F3: a held sample keeps the state and is checked when the hold ends."""

    async def test_resync_sample_keeps_state_and_rechecks_after_hold(self) -> None:
        manager = self.make_manager()
        await self.update(manager, 0, "a", "b")
        self.assertTrue(manager.data.proximity)
        manager.hass.bus.events.clear()

        await self.update(manager, 700, "a")  # base quiet for more than 600 s

        self.assertEqual("resync_a", manager.data.last_error)
        self.assertTrue(manager.data.data_valid)
        self.assertTrue(manager.data.proximity)
        self.assertEqual([], manager.hass.bus.names())
        self.assertEqual(1, len(self.timers.calls))
        self.assertAlmostEqual(61.0, self.timers.calls[0].delay)

        self.clock.at(761)
        self.timers.calls[0].action(self.clock.now)
        await self.run_scheduled(manager)

        self.assertIsNone(manager.data.last_error)
        self.assertTrue(manager.data.data_valid)
        self.assertTrue(manager.data.proximity)
        self.assertEqual([], manager.hass.bus.names())

    async def test_position_held_during_resync_is_applied_when_hold_ends(self) -> None:
        manager = self.make_manager()
        await self.update(manager, 0, "a", "b")
        manager.hass.bus.events.clear()

        self.positions["person.tracker"] = FAR
        await self.update(manager, 700, "b")

        self.assertTrue(manager.data.proximity)
        self.assertEqual([], manager.hass.bus.names())

        self.clock.at(761)
        self.timers.calls[0].action(self.clock.now)
        await self.run_scheduled(manager)

        self.assertFalse(manager.data.proximity)
        self.assertEqual([LEAVE], manager.hass.bus.names())

    async def test_stop_cancels_hold_end_check(self) -> None:
        manager = self.make_manager()
        await self.update(manager, 0, "a", "b")
        await self.update(manager, 700, "a")

        await manager.async_stop()

        self.assertTrue(self.timers.calls[0].cancelled)

    async def test_refresh_button_during_hold_keeps_state(self) -> None:
        manager = self.make_manager()
        await self.update(manager, 0, "a", "b")
        manager.hass.bus.events.clear()
        self.positions["person.tracker"] = FAR
        await self.update(manager, 700, "b")  # held far fix

        self.clock.at(710)
        await manager.async_force_refresh()

        self.assertTrue(manager.data.proximity)
        self.assertEqual("resync_b", manager.data.last_error)
        self.assertEqual([], manager.hass.bus.names())

        self.clock.at(761)
        self.timers.calls[-1].action(self.clock.now)
        await self.run_scheduled(manager)

        self.assertFalse(manager.data.proximity)
        self.assertEqual([LEAVE], manager.hass.bus.names())

    async def test_other_side_update_during_hold_waits_for_hold_end(self) -> None:
        manager = self.make_manager()
        await self.update(manager, 0, "a", "b")
        await self.update(manager, 300, "a")
        self.positions["person.tracker"] = FAR
        await self.update(manager, 700, "b")  # tracker quiet for 700 s: held
        manager.hass.bus.events.clear()

        await self.update(manager, 705, "a")

        self.assertTrue(manager.data.proximity)
        self.assertEqual("resync_b", manager.data.last_error)
        self.assertEqual([], manager.hass.bus.names())
        # The base update is genuine and still counted (older entries pruned).
        self.assertEqual(START + timedelta(seconds=705), manager.a_update_history[-1])
        self.assertEqual(1, len(manager.b_update_history))

    async def test_speed_filtered_sample_still_marks_data_invalid(self) -> None:
        manager = self.make_manager(max_speed_kmh=150)
        await self.update(manager, 0, "a", "b")

        self.positions["person.tracker"] = FAR  # 1.4 km in 10 s
        await self.update(manager, 10, "b")

        self.assertFalse(manager.data.data_valid)
        self.assertEqual("speed_filtered_b", manager.data.last_error)
        self.assertEqual([], self.timers.calls)


class RestoreStateTests(_Case):
    """F4: a restart or reload continues the saved proximity state."""

    async def test_saved_on_state_continues_without_new_enter(self) -> None:
        entered = (START - timedelta(minutes=30)).isoformat()
        self.saved_state(
            {
                "proximity": True,
                "raw_proximity": True,
                "proximity_update_count": 4,
                "proximity_since": entered,
                "last_changed": entered,
                "last_entered": entered,
                "last_left": None,
            }
        )
        manager = self.make_manager(min_updates_for_proximity=3)

        await manager.async_start()

        self.assertEqual([], manager.hass.bus.names())
        self.assertTrue(manager.data.proximity)
        self.assertEqual(4, manager.data.proximity_update_count)
        self.assertEqual(entered, manager.data.last_entered)
        self.assertEqual(30 * 60, manager.proximity_duration_seconds())

    async def test_saved_unreliable_nearby_state_does_not_repeat_event(self) -> None:
        self.saved_state(
            {"proximity": False, "raw_proximity": True, "proximity_update_count": 0}
        )
        manager = self.make_manager(min_updates_for_proximity=3)

        await manager.async_start()

        self.assertEqual([], manager.hass.bus.names())
        self.assertFalse(manager.data.proximity)
        self.assertTrue(manager._raw_proximity)

    async def test_registry_indexed_restore_data_is_read(self) -> None:
        self.saved_state(
            {"proximity": True, "raw_proximity": True, "proximity_update_count": 2},
            registry_indexed=True,
        )
        manager = self.make_manager(min_updates_for_proximity=3)

        await manager.async_start()

        self.assertEqual([], manager.hass.bus.names())
        self.assertTrue(manager.data.proximity)
        self.assertEqual(2, manager.data.proximity_update_count)

    async def test_saved_on_state_ends_with_one_leave_when_now_apart(self) -> None:
        self.saved_state(
            {"proximity": True, "raw_proximity": True, "proximity_update_count": 2}
        )
        manager = self.make_manager()
        self.positions["person.tracker"] = FAR

        await manager.async_start()

        self.assertEqual([LEAVE], manager.hass.bus.names())
        self.assertFalse(manager.data.proximity)
        self.assertEqual(0, manager.data.proximity_update_count)

    async def test_start_without_saved_state_is_unchanged(self) -> None:
        manager = self.make_manager(min_updates_for_proximity=3)

        await manager.async_start()

        self.assertEqual([ENTER_UNRELIABLE], manager.hass.bus.names())
        self.assertFalse(manager.data.proximity)

    async def test_malformed_saved_state_is_ignored(self) -> None:
        self.saved_state({"proximity": "on", "proximity_update_count": 3})
        manager = self.make_manager(min_updates_for_proximity=3)

        await manager.async_start()

        self.assertEqual([ENTER_UNRELIABLE], manager.hass.bus.names())
        self.assertEqual(0, manager.data.proximity_update_count)

    async def test_saved_state_of_disabled_sensor_is_ignored(self) -> None:
        self.saved_state(
            {"proximity": True, "raw_proximity": True, "proximity_update_count": 2},
            disabled=True,
        )
        manager = self.make_manager()
        self.positions["person.tracker"] = FAR

        await manager.async_start()

        self.assertEqual([], manager.hass.bus.names())
        self.assertFalse(manager.data.proximity)

    async def test_disabled_binary_sensor_saves_nothing(self) -> None:
        manager = self.make_manager()
        entity = binary_sensor_module.MemberAdjacencyProximityBinary(manager)

        entity.registry_entry = types.SimpleNamespace(disabled=True)
        self.assertIsNone(entity.extra_restore_state_data)

        entity.registry_entry = types.SimpleNamespace(disabled=False)
        self.assertEqual(
            manager.restore_snapshot(), entity.extra_restore_state_data.as_dict()
        )

    async def test_restored_on_state_is_not_a_proximity_update(self) -> None:
        self.saved_state(
            {"proximity": True, "raw_proximity": True, "proximity_update_count": 2}
        )
        manager = self.make_manager(require_reliable_proximity=False)

        await manager.async_start()

        self.assertEqual([], manager.hass.bus.names())
        self.assertEqual(2, manager.data.proximity_update_count)

    async def test_binary_sensor_saves_what_the_manager_restores(self) -> None:
        restore_entity = sys.modules["homeassistant.helpers.restore_state"].RestoreEntity
        first = self.make_manager()
        await self.update(first, 0, "a", "b")
        self.assertTrue(first.data.proximity)
        entity = binary_sensor_module.MemberAdjacencyProximityBinary(first)
        entity.hass = first.hass

        self.assertIsInstance(entity, restore_entity)
        await entity.async_added_to_hass()
        self.assertTrue(entity.restore_registered)

        self.saved_state(entity.extra_restore_state_data.as_dict())
        self.clock.at(600)
        second = self.make_manager()
        await second.async_start()

        self.assertEqual([], second.hass.bus.names())
        self.assertTrue(second.data.proximity)
        self.assertEqual(first.data.last_entered, second.data.last_entered)
        self.assertEqual(600, second.proximity_duration_seconds())


class ConvergenceTests(_Case):
    """F5 and F6: convergence speed."""

    async def test_zero_max_speed_turns_off_convergence_check(self) -> None:
        manager = manager_module.AdjacencyManager(
            FakeHass(),
            FakeEntry(data={"base_entity": "person.a", "tracker_entity": "person.b"}),
        )
        manager.min_updates_for_proximity = 1
        manager.a_update_history = [START]
        manager.b_update_history = [START]
        manager._prev_distance_m = 1000.0
        manager._prev_distance_time = START - timedelta(seconds=1)

        manager.max_speed_kmh = 150
        self.assertFalse(manager._check_proximity_reliability(0.0)[0])

        manager.max_speed_kmh = 0
        reliable, reason = manager._check_proximity_reliability(0.0)

        self.assertTrue(reliable)
        self.assertIsNone(reason)
        self.assertAlmostEqual(3600.0, manager.data.convergence_speed_kmh)

    async def test_convergence_uses_previous_fix_of_moved_side(self) -> None:
        manager = self.make_manager(
            entry_threshold_m=600, exit_threshold_m=800, max_speed_kmh=150
        )
        self.positions["person.base"] = (37.500000, 127.0)
        self.positions["person.tracker"] = (37.509000, 127.0)  # about 1 km
        await self.update(manager, 0, "a", "b")
        await self.update(manager, 55, "b")

        self.positions["person.base"] = (37.504500, 127.0)  # 500 m in 60 s
        await self.update(manager, 60, "a")

        self.assertAlmostEqual(30.0, manager.data.convergence_speed_kmh, delta=0.5)
        self.assertTrue(manager.data.proximity_reliable)
        self.assertIn(ENTER, manager.hass.bus.names())


class ForcedRefreshTests(_Case):
    """F9: startup and refresh-button recalculations are not location updates."""

    async def test_refresh_button_is_not_counted_as_location_update(self) -> None:
        manager = self.make_manager(min_updates_for_proximity=3)

        for seconds in (0, 1, 2):
            self.clock.at(seconds)
            await manager.async_force_refresh()

        self.assertEqual([], manager.a_update_history)
        self.assertEqual([], manager.b_update_history)
        self.assertFalse(manager.data.proximity)
        self.assertNotIn(ENTER, manager.hass.bus.names())

    async def test_forced_refresh_does_not_hide_quiet_source(self) -> None:
        manager = self.make_manager()
        await self.update(manager, 0, "a", "b")
        self.clock.at(500)
        await manager.async_force_refresh()

        await self.update(manager, 700, "a")

        self.assertEqual("resync_a", manager.data.last_error)

    async def test_force_refresh_counts_debounced_update_once(self) -> None:
        manager = self.make_manager(debounce_seconds=2)
        manager.request_refresh("person.base")

        await manager.async_force_refresh()

        self.assertEqual(1, len(manager.a_update_history))
        self.assertEqual(0, len(manager.b_update_history))
        self.assertTrue(self.timers.calls[0].cancelled)

    async def test_forced_refresh_while_on_is_not_a_proximity_update(self) -> None:
        manager = self.make_manager()
        await self.update(manager, 0, "a", "b")
        manager.hass.bus.events.clear()

        self.clock.at(30)
        await manager.async_force_refresh()

        self.assertEqual([], manager.hass.bus.names())
        self.assertEqual(1, manager.data.proximity_update_count)

        await self.update(manager, 40, "a")

        self.assertEqual([UPDATE], manager.hass.bus.names())
        self.assertEqual(2, manager.data.proximity_update_count)


class UnloadTests(_Case):
    """A stopped manager does nothing; unload stops it before the platforms."""

    async def test_stopped_manager_ignores_late_refreshes(self) -> None:
        manager = self.make_manager(debounce_seconds=2)
        await self.update(manager, 0, "a", "b")
        manager.hass.bus.events.clear()
        manager.request_refresh("person.base")

        await manager.async_stop()
        self.positions["person.tracker"] = FAR
        self.clock.at(700)
        await manager.async_force_refresh()
        manager.request_refresh("person.tracker")
        await self.update(manager, 710, "b")

        self.assertEqual([], manager.hass.bus.names())
        self.assertTrue(manager.data.proximity)
        self.assertEqual(set(), manager._pending_changed_sides)
        self.assertEqual({}, manager._hold_end_timers)
        self.assertEqual(1, len(self.timers.calls))  # only the first debounce

    async def test_unload_stops_manager_before_platforms(self) -> None:
        manager = self.make_manager()
        order: list[str] = []

        async def _unload_platforms(_entry, _platforms) -> bool:
            order.append("stopped" if manager._stopped else "running")
            return True

        hass = FakeHass()
        hass.data = {package.DOMAIN: {"entry-test": manager}}
        hass.config_entries = types.SimpleNamespace(
            async_unload_platforms=_unload_platforms
        )

        self.assertTrue(await package.async_unload_entry(hass, manager.entry))
        self.assertEqual(["stopped"], order)
        self.assertNotIn("entry-test", hass.data[package.DOMAIN])


class DistanceFailureTests(_Case):
    """F10: a distance that cannot be computed does not crash the refresh."""

    async def test_unconverged_distance_marks_sample_invalid(self) -> None:
        manager = self.make_manager()
        self._patch(runtime_module, "ha_distance", lambda *_args: None)

        await self.update(manager, 0, "a", "b")

        self.assertFalse(manager.data.data_valid)
        self.assertEqual("distance_unavailable", manager.data.last_error)
        self.assertEqual([], manager.hass.bus.names())

    async def test_movement_without_distance_keeps_new_fix(self) -> None:
        manager = self.make_manager(max_speed_kmh=150)
        await self.update(manager, 0, "a", "b")
        self._patch(manager_module, "ha_distance", lambda *_args: None)
        self.clock.at(30)

        result = manager._update_movement((37.6, 127.0), None)

        self.assertIsNone(result)
        self.assertIsNone(manager.a_speed_kmh)
        self.assertEqual((37.6, 127.0), manager.a_prev_coords)

    async def test_failed_platform_setup_stops_manager(self) -> None:
        unsubscribed: list[bool] = []
        self._patch(
            runtime_module,
            "async_track_state_change_event",
            lambda *_args, **_kwargs: (lambda: unsubscribed.append(True)),
        )
        hass = FakeHass()
        hass.data = {}
        hass.config_entries = types.SimpleNamespace(
            async_forward_entry_setups=AsyncMock(side_effect=RuntimeError("failed"))
        )
        entry = FakeEntry(
            data={"base_entity": "person.base", "tracker_entity": "person.tracker"}
        )

        with self.assertRaises(RuntimeError):
            await package.async_setup_entry(hass, entry)

        self.assertNotIn(entry.entry_id, hass.data.get(package.DOMAIN, {}))
        self.assertEqual([True], unsubscribed)


class SourceUpdateRequestTests(_Case):
    """F7: the refresh button reaches the phone's notify service."""

    def phone_registries(self) -> None:
        entity = types.SimpleNamespace(device_id="phone-device")
        device = types.SimpleNamespace(
            identifiers={("mobile_app", "a1b2c3")},
            name="Bobby's iPhone",
            name_by_user="바비 폰",
        )
        entities = types.SimpleNamespace(
            async_get=lambda entity_id: (
                entity if entity_id == "device_tracker.bobby_phone" else None
            ),
            async_get_entity_id=lambda *_args: None,
        )
        devices = types.SimpleNamespace(
            async_get=lambda device_id: device if device_id == "phone-device" else None
        )
        self._patch(manager_module.er, "async_get", lambda _hass: entities)
        self._patch(manager_module.dr, "async_get", lambda _hass: devices)

    def make_requesting_manager(self, services: set[tuple[str, str]]):
        manager = self.make_manager()
        manager.hass.services.has_service = (
            lambda domain, service: (domain, service) in services
        )
        manager.hass.services.async_call = AsyncMock()
        return manager

    @staticmethod
    def calls(manager) -> list[tuple]:
        return [call.args for call in manager.hass.services.async_call.await_args_list]

    async def test_refresh_button_reaches_phone_notify_service(self) -> None:
        self.phone_registries()
        manager = self.make_requesting_manager(
            {("notify", "mobile_app_bobby_s_iphone"), ("homeassistant", "update_entity")}
        )

        await manager.async_request_source_update("device_tracker.bobby_phone")

        self.assertEqual(
            [
                ("notify", "mobile_app_bobby_s_iphone", {"message": "request_location_update"}),
                ("homeassistant", "update_entity", {"entity_id": "device_tracker.bobby_phone"}),
            ],
            self.calls(manager),
        )

    async def test_person_is_followed_to_its_phone(self) -> None:
        self.phone_registries()
        manager = self.make_requesting_manager(
            {("notify", "mobile_app_bobby_s_iphone"), ("homeassistant", "update_entity")}
        )
        person = types.SimpleNamespace(
            state="home", attributes={"source": "device_tracker.bobby_phone"}
        )
        manager.hass.states = types.SimpleNamespace(
            get=lambda entity_id: person if entity_id == "person.bobby" else None
        )

        await manager.async_request_source_update("person.bobby")

        self.assertEqual(
            [
                ("notify", "mobile_app_bobby_s_iphone", {"message": "request_location_update"}),
                ("homeassistant", "update_entity", {"entity_id": "person.bobby"}),
            ],
            self.calls(manager),
        )

    async def test_registry_identifier_service_is_still_a_fallback(self) -> None:
        self.phone_registries()
        manager = self.make_requesting_manager({("notify", "mobile_app_a1b2c3")})

        await manager.async_request_source_update("device_tracker.bobby_phone")

        self.assertEqual(
            [("notify", "mobile_app_a1b2c3", {"message": "request_location_update"})],
            self.calls(manager),
        )


class DurationSensorTests(_Case):
    """F8: the duration sensor keeps counting while two people stay together."""

    def track_platform_helpers(self) -> tuple[list, list]:
        intervals: list[types.SimpleNamespace] = []
        listeners: list = []

        def track(_hass, action, interval):
            handle = types.SimpleNamespace(
                action=action, interval=interval, cancelled=False
            )
            intervals.append(handle)

            def _cancel() -> None:
                handle.cancelled = True

            return _cancel

        def connect(_hass, _signal, target):
            listeners.append(target)
            return lambda: None

        self._patch(sensor_module, "async_track_time_interval", track)
        self._patch(sensor_module, "async_dispatcher_connect", connect)
        return intervals, listeners

    async def test_duration_sensor_ticks_each_minute_while_on(self) -> None:
        intervals, listeners = self.track_platform_helpers()
        manager = self.make_manager()
        await self.update(manager, 0, "a", "b")
        sensor = sensor_module.MemberAdjacencyProximityDurationSensor(manager)
        sensor.hass = manager.hass

        await sensor.async_added_to_hass()

        self.assertEqual(1, len(intervals))
        self.assertEqual(timedelta(minutes=1), intervals[0].interval)

        self.clock.at(300)
        intervals[0].action(self.clock.now)

        self.assertEqual("5분", sensor.native_value)
        self.assertEqual(1, sensor.writes)

        self.positions["person.tracker"] = FAR
        await self.update(manager, 310, "b")
        listeners[0]()

        self.assertTrue(intervals[0].cancelled)
        self.assertEqual(2, sensor.writes)

    async def test_duration_sensor_does_not_tick_while_apart(self) -> None:
        intervals, _listeners = self.track_platform_helpers()
        manager = self.make_manager()
        self.positions["person.tracker"] = FAR
        await self.update(manager, 0, "a", "b")
        sensor = sensor_module.MemberAdjacencyProximityDurationSensor(manager)
        sensor.hass = manager.hass

        await sensor.async_added_to_hass()

        self.assertEqual([], intervals)

    def test_ticking_duration_attributes_are_not_recorded(self) -> None:
        unrecorded = (
            sensor_module.MemberAdjacencyProximityDurationSensor._unrecorded_attributes
        )

        self.assertEqual(
            frozenset({"proximity_duration_min", "proximity_duration_human"}),
            unrecorded,
        )
        self.assertFalse(
            getattr(sensor_module.MemberAdjacencyDistanceSensor, "_unrecorded_attributes", frozenset())
        )


class ConfigFlowCoordinateTests(unittest.TestCase):
    """F11: the setup form uses the runtime coordinate check."""

    def test_config_flow_uses_manager_coordinate_validation(self) -> None:
        tree = ast.parse((COMPONENT_ROOT / "config_flow.py").read_text(encoding="utf-8"))
        defined = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        imported = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.level == 1
            and node.module == "manager"
            for alias in node.names
        }

        self.assertNotIn("_try_get_coords_from_state", defined)
        self.assertIn("_try_get_coords_from_state", imported)


if __name__ == "__main__":
    unittest.main()
