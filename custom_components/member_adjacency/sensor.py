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

    async_add_entities(
        [
            MemberAdjacencyDistanceSensor(mgr),
            MemberAdjacencyBucketSensor(mgr),
            MemberAdjacencyProximityDurationSensor(mgr),
        ]
    )


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

    def _display(self, meters: float) -> tuple[float, str, str]:
        """
        표시용 값/단위/텍스트.
        - force_meters=True => 항상 m
        - 아니면 1000m 이상이면 km 표시
        """
        if self.mgr.force_meters or meters < 1000:
            v = _round1(meters)
            u = "m"
            return v, u, f"{v} m"

        v = _round1(meters / 1000.0)
        u = "km"
        return v, u, f"{v} km"

    def _common_attrs(self) -> dict[str, Any]:
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

            # ✅ 저장/통계용(항상 meters)
            "distance_m": None if d_m is None else _round1(d_m),
            "distance_km": None if d_m is None else _round1(d_m / 1000.0),

            # ✅ 표시용(자동 m/km 전환)
            "display_value": display_value,
            "display_unit": display_unit,
            "display_text": display_text,

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
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arrow-left-right"

    def __init__(self, mgr: AdjacencyManager) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_distance"
        self._attr_name = f"{DEFAULT_NAME_KO} 거리"

    @property
    def native_unit_of_measurement(self) -> str | None:
        # ✅ 항상 meters로 고정 (통계 안정화)
        return UnitOfLength.METERS

    @property
    def native_value(self) -> float | None:
        # ✅ 항상 meters로 저장 (표시는 attributes에서)
        d = self.mgr.data.distance_m
        if d is None:
            return None
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
