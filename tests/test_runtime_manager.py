from __future__ import annotations

import importlib
import unittest

from tests.test_manager import FakeEntry, FakeHass


runtime_module = importlib.import_module(
    "custom_components.member_adjacency.runtime_manager"
)
AdjacencyManager = runtime_module.AdjacencyManager


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def async_fire(self, event_type: str, data: dict[str, object]) -> None:
        self.events.append((event_type, data))


class RuntimeManagerTests(unittest.IsolatedAsyncioTestCase):
    def make_manager(self, *, min_updates: int = 1) -> AdjacencyManager:
        entry = FakeEntry(
            data={
                "base_entity": "person.base",
                "tracker_entity": "person.tracker",
                "entry_threshold_m": 500,
                "exit_threshold_m": 600,
                "min_updates_for_proximity": min_updates,
                "require_reliable_proximity": True,
                "debounce_seconds": 0,
                "max_speed_kmh": 0,
            }
        )
        hass = FakeHass()
        hass.bus = RecordingBus()
        manager = AdjacencyManager(hass, entry)
        coordinates = {
            "person.base": ((37.500000, 127.000000), 5.0),
            "person.tracker": ((37.500100, 127.000000), 5.0),
        }
        manager._coords_and_acc = lambda entity_id: coordinates[entity_id]  # type: ignore[method-assign]
        return manager

    async def test_only_changed_source_updates_history_and_fix_time(self) -> None:
        manager = self.make_manager()

        await manager.async_refresh(changed_sides={"a"})

        self.assertEqual(1, len(manager.a_update_history))
        self.assertEqual(0, len(manager.b_update_history))
        self.assertIsNotNone(manager.a_last_fix)
        self.assertIsNone(manager.b_last_fix)
        self.assertFalse(manager.data.proximity_reliable)

        await manager.async_refresh(changed_sides={"b"})

        self.assertEqual(1, len(manager.a_update_history))
        self.assertEqual(1, len(manager.b_update_history))
        self.assertIsNotNone(manager.b_last_fix)
        self.assertTrue(manager.data.proximity_reliable)

    async def test_reliable_transition_fires_normal_enter_after_unreliable_entry(self) -> None:
        manager = self.make_manager(min_updates=2)

        await manager.async_refresh(force_both=True)

        self.assertTrue(manager._raw_proximity)
        self.assertFalse(manager.data.proximity)
        self.assertEqual(
            [runtime_module.EVENT_ENTER_UNRELIABLE],
            [event_type for event_type, _data in manager.hass.bus.events],
        )

        await manager.async_refresh(force_both=True)

        event_types = [event_type for event_type, _data in manager.hass.bus.events]
        self.assertTrue(manager.data.proximity)
        self.assertIn(runtime_module.EVENT_ENTER, event_types)
        self.assertIn(runtime_module.EVENT_PROXIMITY_UPDATE, event_types)
        self.assertEqual(1, manager.data.proximity_update_count)

    async def test_invalid_sample_marks_entities_unavailable_without_false_leave(self) -> None:
        manager = self.make_manager()
        await manager.async_refresh(force_both=True)
        self.assertTrue(manager.data.proximity)

        manager._coords_and_acc = lambda entity_id: (  # type: ignore[method-assign]
            (None, None) if entity_id == "person.base" else ((37.5, 127.0), 5.0)
        )
        before = list(manager.hass.bus.events)

        await manager.async_refresh(changed_sides={"a"})

        self.assertFalse(manager.data.data_valid)
        self.assertEqual("missing_coords", manager.data.last_error)
        self.assertTrue(manager.data.proximity)
        self.assertEqual(before, manager.hass.bus.events)


if __name__ == "__main__":
    unittest.main()
