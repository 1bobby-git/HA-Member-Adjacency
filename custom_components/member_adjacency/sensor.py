from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
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
    mgr: AdjacencyManager = hass.data[DOMAIN][entry.entry_id]

    ent_reg = er.async_get(hass)
    pair_key = mgr.pair_key

    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_distance",
        suggested_object_id=f"member_adjacency_{pair_key}",
        config_entry=entry,
    )
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_bucket",
        suggested_object_id=f"member_adjacency_{pair_key}_bucket",
        config_entry=entry,
    )
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_proximity_duration",
        suggested_object_id=f"member_adjacency_{pair_key}_proximity_duration",
        config_entry=entry,
    )

    async_add_entities([
        MemberAdjacencyDistanceSensor(mgr),
        MemberAdjacencyBucketSensor(mgr),
        MemberAdjacencyProximityDurationSensor(mgr),
    ])


class _Base(SensorEntity):
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

    def _common_attrs(self) -> dict[str, Any]:
        d = self.mgr.data.distance_m
        return {
            "entity_a": self.mgr.entity_a,
            "entity_b": self.mgr.entity_b,
            "entry_threshold_m": self.mgr.entry_th,
            "exit_threshold_m": self.mgr.exit_th,
            "debounce_seconds": self.mgr.debounce_s,
            "max_accuracy_m": self.mgr.max_acc_m,
            "force_meters": self.mgr.force_meters,
            "data_valid": self.mgr.data.data_valid,
            "last_valid_updated": self.mgr.data.last_valid_updated,
            "last_error": self.mgr.data.last_error,
            "accuracy_a": None if self.mgr.data.accuracy_a is None else _round1(self.mgr.data.accuracy_a),
            "accuracy_b": None if self.mgr.data.accuracy_b is None else _round1(self.mgr.data.accuracy_b),
            "distance_m": None if d is None else _round1(d),
            "distance_km": None if d is None else _round1(d / 1000.0),
            "bucket": self.mgr.data.bucket,
            "proximity": self.mgr.data.proximity,
            "proximity_duration_min": _round1(self.mgr.proximity_duration_minutes()),
            "proximity_duration_human": self.mgr.proximity_duration_human(),
            "last_changed": self.mgr.data.last_changed,
            "last_entered": self.mgr.data.last_entered,
            "last_left": self.mgr.data.last_left,
        }


class MemberAdjacencyDistanceSensor(_Base):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arrow-left-right"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_distance"
        self._attr_name = f"{DEFAULT_NAME_KO} 거리"

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.mgr.force_meters:
            return UnitOfLength.METERS
        d = self.mgr.data.distance_m
        if d is not None and d >= 1000:
            return UnitOfLength.KILOMETERS
        return UnitOfLength.METERS

    @property
    def native_value(self) -> float | None:
        d = self.mgr.data.distance_m
        if d is None:
            return None

        # ✅ 표시 정밀도: 소수점 1자리 고정
        if self.mgr.force_meters:
            return _round1(d)
        if d >= 1000:
            return _round1(d / 1000.0)
        return _round1(d)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()


class MemberAdjacencyBucketSensor(_Base):
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_bucket"
        self._attr_name = f"{DEFAULT_NAME_KO} 구간"

    @property
    def native_value(self) -> str | None:
        return self.mgr.data.bucket

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()


class MemberAdjacencyProximityDurationSensor(_Base):
    """
    ✅ 사용자 요청: 0.0 min 같은 숫자 대신
    - "5분"
    - "1시간 20분"
    형태로 표시
    """
    _attr_icon = "mdi:timer-outline"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_proximity_duration"
        self._attr_name = f"{DEFAULT_NAME_KO} 근접 지속시간"

    @property
    def native_value(self) -> str:
        return self.mgr.proximity_duration_human()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._common_attrs()
