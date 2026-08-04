from __future__ import annotations

import asyncio
import importlib
import logging
import math
import sys
import types
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock


def _install_homeassistant_stubs() -> None:
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
    event = types.ModuleType("homeassistant.helpers.event")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    util = types.ModuleType("homeassistant.util")
    dt_mod = types.ModuleType("homeassistant.util.dt")
    location = types.ModuleType("homeassistant.util.location")

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    class ServiceNotFound(Exception):
        pass

    def callback(func):
        return func

    def async_dispatcher_send(*_args, **_kwargs):
        return None

    def async_call_later(*_args, **_kwargs):
        return lambda: None

    def async_track_state_change_event(*_args, **_kwargs):
        return lambda: None

    def async_get(_hass):
        return _Registry()

    def utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_m = 6_371_000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(d_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        )
        return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    config_entries.ConfigEntry = ConfigEntry
    core.HomeAssistant = HomeAssistant
    core.callback = callback
    exceptions.ServiceNotFound = ServiceNotFound
    dispatcher.async_dispatcher_send = async_dispatcher_send
    event.async_call_later = async_call_later
    event.async_track_state_change_event = async_track_state_change_event
    device_registry.async_get = async_get
    entity_registry.async_get = async_get
    dt_mod.utcnow = utcnow
    location.distance = distance
    helpers.dispatcher = dispatcher
    helpers.event = event
    helpers.device_registry = device_registry
    helpers.entity_registry = entity_registry
    util.dt = dt_mod
    util.location = location
    homeassistant.config_entries = config_entries
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    homeassistant.util = util

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.dispatcher": dispatcher,
        "homeassistant.helpers.event": event,
        "homeassistant.helpers.device_registry": device_registry,
        "homeassistant.helpers.entity_registry": entity_registry,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_mod,
        "homeassistant.util.location": location,
    }
    sys.modules.update(modules)


class _Registry:
    def async_get(self, _key):
        return None


@dataclass
class FakeEntry:
    data: dict[str, object]
    options: dict[str, object] = field(default_factory=dict)
    entry_id: str = "entry-test"


class FakeServices:
    def __init__(self) -> None:
        self.has_service = lambda _domain, _service: False
        self.async_call = AsyncMock()


class FakeHass:
    def __init__(self) -> None:
        self.services = FakeServices()
        self.states = types.SimpleNamespace(get=lambda _entity_id: None)
        self.bus = types.SimpleNamespace(async_fire=lambda *_args, **_kwargs: None)

    def async_create_task(self, coro):
        return asyncio.create_task(coro)


_install_homeassistant_stubs()
manager_module = importlib.import_module("custom_components.member_adjacency.manager")
AdjacencyManager = manager_module.AdjacencyManager


def make_manager() -> AdjacencyManager:
    entry = FakeEntry(
        data={
            "base_entity": "person.base",
            "tracker_entity": "person.tracker",
        }
    )
    return AdjacencyManager(FakeHass(), entry)


class RequestSourceUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_notify_failure_logs_actionable_debug_context(self) -> None:
        mgr = make_manager()
        mgr._mobile_app_identifier_from_entity = lambda _entity_id: "Phone ABC"  # type: ignore[method-assign]
        mgr.hass.services.has_service = lambda domain, service: (
            domain == "notify" and service == "mobile_app_phone_abc"
        )
        mgr.hass.services.async_call = AsyncMock(side_effect=RuntimeError("notify denied"))

        with self.assertLogs("custom_components.member_adjacency.manager", level="DEBUG") as logs:
            await mgr.async_request_source_update("person.test")

        records = logs.records
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("member_adjacency.request_location_update_failed", record.getMessage())
        self.assertEqual(logging.DEBUG, record.levelno)
        self.assertEqual("person.test", record.entity_id)
        self.assertEqual("notify.mobile_app_phone_abc", record.service)
        self.assertEqual("RuntimeError", record.exception_type)
        self.assertEqual("notify denied", record.exception_msg)
        self.assertIsNotNone(record.exc_info)
        self.assertFalse(hasattr(record, "data"))

    async def test_update_entity_failure_logs_actionable_debug_context(self) -> None:
        mgr = make_manager()
        mgr._mobile_app_identifier_from_entity = lambda _entity_id: None  # type: ignore[method-assign]
        mgr.hass.services.has_service = lambda domain, service: (
            domain == "homeassistant" and service == "update_entity"
        )
        mgr.hass.services.async_call = AsyncMock(side_effect=RuntimeError("update denied"))

        with self.assertLogs("custom_components.member_adjacency.manager", level="DEBUG") as logs:
            await mgr.async_request_source_update("person.test")

        records = logs.records
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("member_adjacency.update_entity_failed", record.getMessage())
        self.assertEqual(logging.DEBUG, record.levelno)
        self.assertEqual("person.test", record.entity_id)
        self.assertEqual("homeassistant.update_entity", record.service)
        self.assertEqual("RuntimeError", record.exception_type)
        self.assertEqual("update denied", record.exception_msg)
        self.assertIsNotNone(record.exc_info)
        self.assertFalse(hasattr(record, "data"))

    async def test_source_failures_do_not_block_local_refresh(self) -> None:
        mgr = make_manager()
        mgr._mobile_app_identifier_from_entity = lambda _entity_id: "Phone ABC"  # type: ignore[method-assign]
        mgr.hass.services.has_service = lambda domain, service: (
            (domain == "notify" and service == "mobile_app_phone_abc")
            or (domain == "homeassistant" and service == "update_entity")
        )
        mgr.hass.services.async_call = AsyncMock(side_effect=RuntimeError("service denied"))
        mgr.async_refresh = AsyncMock()  # type: ignore[method-assign]

        with self.assertLogs("custom_components.member_adjacency.manager", level="DEBUG") as logs:
            await mgr.async_force_refresh_with_source_update()

        self.assertEqual(
            [
                ("person.base", "notify.mobile_app_phone_abc"),
                ("person.base", "homeassistant.update_entity"),
                ("person.tracker", "notify.mobile_app_phone_abc"),
                ("person.tracker", "homeassistant.update_entity"),
            ],
            [(record.entity_id, record.service) for record in logs.records],
        )
        self.assertTrue(all(record.exc_info for record in logs.records))
        mgr.async_refresh.assert_awaited_once()


class ManagerDecisionPathTests(unittest.TestCase):
    def test_update_movement_filters_unrealistic_speed_without_redesign(self) -> None:
        mgr = make_manager()
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
        original_utcnow = manager_module.dt_util.utcnow
        try:
            manager_module.dt_util.utcnow = lambda: now
            mgr.max_speed_kmh = 1
            mgr.a_prev_coords = (37.0, 127.0)
            mgr.a_last_fix = now - timedelta(minutes=10)

            result = mgr._update_movement((38.0, 128.0), (37.0, 127.0))
        finally:
            manager_module.dt_util.utcnow = original_utcnow

        self.assertEqual("speed_filtered_a", result)
        self.assertEqual((38.0, 128.0), mgr.a_prev_coords)
        self.assertEqual(now, mgr.a_last_fix)

    def test_proximity_reliability_requires_both_recent_histories(self) -> None:
        mgr = make_manager()
        mgr.min_updates_for_proximity = 2
        mgr.update_window_s = 300
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
        original_utcnow = manager_module.dt_util.utcnow
        try:
            manager_module.dt_util.utcnow = lambda: now
            mgr.a_update_history = [now - timedelta(seconds=10), now - timedelta(seconds=20)]
            mgr.b_update_history = [now - timedelta(seconds=10)]

            reliable, reason = mgr._check_proximity_reliability(50.0)
        finally:
            manager_module.dt_util.utcnow = original_utcnow

        self.assertFalse(reliable)
        self.assertEqual("insufficient_updates_b (1<2)", reason)
        self.assertEqual(2, mgr.data.a_updates_in_window)
        self.assertEqual(1, mgr.data.b_updates_in_window)


if __name__ == "__main__":
    unittest.main()
