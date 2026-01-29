"""
Sensor platform for the Member Adjacency component.

This module exposes multiple sensor entities representing the distance
between two tracked entities, the bucketed distance category, the
duration of the current proximity state and the estimated speeds of
each individual entity.  All sensors share a common base class which
subscribes to update signals from the underlying :class:`AdjacencyManager`.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, DEFAULT_NAME_KO
from .manager import AdjacencyManager


def _round1(x: float) -> float:
    return round(float(x), 1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up Member Adjacency sensors for a config entry."""
    mgr: AdjacencyManager = hass.data[DOMAIN][entry.entry_id]

    ent_reg = er.async_get(hass)
    pair_key = mgr.pair_key

    # Ensure all sensor entities are created in the entity registry
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_distance",
        suggested_object_id=f"member_adjacency_{pair_key}",
        config_entry=entry,
    )
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_bucket",
        suggested_object_id=f"member_adjacency_{pair_key}_bucket",
        config_entry=entry,
    )
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_proximity_duration",
        suggested_object_id=f"member_adjacency_{pair_key}_proximity_duration",
        config_entry=entry,
    )
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_speed_a",
        suggested_object_id=f"member_adjacency_{pair_key}_speed_a",
        config_entry=entry,
    )
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_speed_b",
        suggested_object_id=f"member_adjacency_{pair_key}_speed_b",
        config_entry=entry,
    )

    async_add_entities(
        [
            MemberAdjacencyDistanceSensor(mgr),
            MemberAdjacencyBucketSensor(mgr),
            MemberAdjacencyProximityDurationSensor(mgr),
            MemberAdjacencySpeedASensor(mgr),
            MemberAdjacencySpeedBSensor(mgr),
        ]
    )


class _Base(SensorEntity):
    """Base class for all Member Adjacency sensors."""

    _attr_should_poll = False

    def __init__(self, mgr: AdjacencyManager) -> None:
        self.mgr = mgr
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        @callback
        def _updated() -> None:
            self.async_write_ha_state()

        self._unsub = async_dispatcher_connect(self.hass, self.mgr.signal, _updated)
        self.async_on_remove(self._unsub)

    @property
    def device_info(self) -> dict[str, Any]:
        return self.mgr.device_info()

    def _display(self, meters: float) -> tuple[float, str, str]:
        """Return display value/unit/text given a distance in meters."""
        if self.mgr.force_meters or meters < 1000:
            v = _round1(meters)
            u = "m"
            return v, u, f"{v} m"
        v = _round1(meters / 1000.0)
        u = "km"
        return v, u, f"{v} km"

    def _common_attrs(self) -> dict[str, Any]:
        """Attributes common to all adjacency sensors."""
        d_m = self.mgr.data.distance_m
        display_value = None
        display_unit = None
        display_text = None
        if d_m is not None:
            dv, du, dt = self._display(d_m)
            display_value = dv
            display_unit = du
            display_text = dt

        return {
            # New semantic naming (기준점/추적대상)
            "base_entity": self.mgr.base_entity,
            "tracker_entity": self.mgr.tracker_entity,
            "base_speed_kmh": None if self.mgr.a_speed_kmh is None else _round1(self.mgr.a_speed_kmh),
            "tracker_speed_kmh": None if self.mgr.b_speed_kmh is None else _round1(self.mgr.b_speed_kmh),
            "base_accuracy_m": None if self.mgr.data.accuracy_a is None else _round1(self.mgr.data.accuracy_a),
            "tracker_accuracy_m": None if self.mgr.data.accuracy_b is None else _round1(self.mgr.data.accuracy_b),
            "base_last_update": self.mgr.a_last_fix.isoformat() if self.mgr.a_last_fix else None,
            "tracker_last_update": self.mgr.b_last_fix.isoformat() if self.mgr.b_last_fix else None,
            "base_updates_recent": self.mgr.data.a_updates_in_window,
            "tracker_updates_recent": self.mgr.data.b_updates_in_window,

            # Legacy aliases (for backward compatibility)
            "entity_a": self.mgr.base_entity,
            "entity_b": self.mgr.tracker_entity,
            "speed_a_kmh": None if self.mgr.a_speed_kmh is None else _round1(self.mgr.a_speed_kmh),
            "speed_b_kmh": None if self.mgr.b_speed_kmh is None else _round1(self.mgr.b_speed_kmh),
            "accuracy_a": None if self.mgr.data.accuracy_a is None else _round1(self.mgr.data.accuracy_a),
            "accuracy_b": None if self.mgr.data.accuracy_b is None else _round1(self.mgr.data.accuracy_b),
            "a_last_fix": self.mgr.a_last_fix.isoformat() if self.mgr.a_last_fix else None,
            "b_last_fix": self.mgr.b_last_fix.isoformat() if self.mgr.b_last_fix else None,
            "a_resync_until": self.mgr.a_resync_until.isoformat() if self.mgr.a_resync_until else None,
            "b_resync_until": self.mgr.b_resync_until.isoformat() if self.mgr.b_resync_until else None,
            "a_updates_in_window": self.mgr.data.a_updates_in_window,
            "b_updates_in_window": self.mgr.data.b_updates_in_window,

            # Configuration
            "entry_threshold_m": self.mgr.entry_th,
            "exit_threshold_m": self.mgr.exit_th,
            "debounce_seconds": self.mgr.debounce_s,
            "max_accuracy_m": self.mgr.max_acc_m,
            "force_meters": self.mgr.force_meters,
            # movement/resync configuration
            "resync_silence_s": self.mgr.resync_silence_s,
            "resync_hold_s": self.mgr.resync_hold_s,
            "max_speed_kmh": self.mgr.max_speed_kmh,
            "min_updates_for_proximity": self.mgr.min_updates_for_proximity,
            "update_window_s": self.mgr.update_window_s,

            # State
            "data_valid": self.mgr.data.data_valid,
            "last_valid_updated": self.mgr.data.last_valid_updated,
            "last_error": self.mgr.data.last_error,

            # raw distance values
            "distance_m": None if d_m is None else _round1(d_m),
            "distance_km": None if d_m is None else _round1(d_m / 1000.0),

            # display values (automatic m/km switching)
            "display_value": display_value,
            "display_unit": display_unit,
            "display_text": display_text,

            # 신뢰도 정보
            "proximity_reliable": self.mgr.data.proximity_reliable,
            "unreliable_reason": self.mgr.data.unreliable_reason,
            "convergence_speed_kmh": None if self.mgr.data.convergence_speed_kmh is None else _round1(self.mgr.data.convergence_speed_kmh),

            "bucket": self.mgr.data.bucket,
            "proximity": self.mgr.data.proximity,
            "proximity_update_count": self.mgr.data.proximity_update_count,
            "proximity_duration_min": _round1(self.mgr.proximity_duration_minutes()),
            "proximity_duration_human": self.mgr.proximity_duration_human(),
            "last_changed": self.mgr.data.last_changed,
            "last_entered": self.mgr.data.last_entered,
            "last_left": self.mgr.data.last_left,
        }


class MemberAdjacencyDistanceSensor(_Base):
    """Sensor reporting the raw distance between two entities in meters."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arrow-left-right"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_distance"
        # Use actual entity names: "바비 → 집 거리"
        self._attr_name = f"{mgr.get_tracker_name()} → {mgr.get_base_name()} 거리"

    @property
    def native_unit_of_measurement(self) -> str | None:
        # always store meters as native unit (statistics stable)
        return UnitOfLength.METERS

    @property
    def native_value(self) -> float | None:
        d = self.mgr.data.distance_m
        if d is None:
            return None
        return _round1(d)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()


class MemberAdjacencyBucketSensor(_Base):
    """Sensor reporting the named bucket for the current distance."""

    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_bucket"
        self._attr_name = f"{mgr.get_tracker_name()} → {mgr.get_base_name()} 구간"

    @property
    def native_value(self) -> str | None:
        return self.mgr.data.bucket

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()


class MemberAdjacencyProximityDurationSensor(_Base):
    """Sensor reporting the duration of the current proximity state."""

    _attr_icon = "mdi:timer-outline"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_proximity_duration"
        self._attr_name = f"{mgr.get_tracker_name()} → {mgr.get_base_name()} 근접 지속시간"

    @property
    def native_value(self) -> str:
        return self.mgr.proximity_duration_human()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()


class MemberAdjacencySpeedASensor(_Base):
    """Sensor reporting the estimated speed of base entity (기준점) in km/h."""

    _attr_device_class = SensorDeviceClass.SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_speed_a"
        # Base entity speed
        self._attr_name = f"{mgr.get_base_name()} 속도"

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "km/h"

    @property
    def native_value(self) -> float | None:
        v = self.mgr.a_speed_kmh
        return None if v is None else _round1(v)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()


class MemberAdjacencySpeedBSensor(_Base):
    """Sensor reporting the estimated speed of tracker entity (추적 대상) in km/h."""

    _attr_device_class = SensorDeviceClass.SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_speed_b"
        # Tracker entity speed
        self._attr_name = f"{mgr.get_tracker_name()} 속도"

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "km/h"

    @property
    def native_value(self) -> float | None:
        v = self.mgr.b_speed_kmh
        return None if v is None else _round1(v)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()