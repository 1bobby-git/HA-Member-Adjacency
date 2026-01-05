from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DEFAULT_NAME_KO
from .coordinator import MemberAdjacencyCoordinator


def _obj_id(entity_id: str) -> str:
    return entity_id.split(".", 1)[1]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coord: MemberAdjacencyCoordinator = hass.data[DOMAIN][entry.entry_id]
    ent_reg = er.async_get(hass)

    entities: list[SensorEntity] = []

    # summary sensors
    ent_reg.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_nearest_distance",
                                suggested_object_id="member_adjacency", config_entry=entry)
    ent_reg.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_nearest_target",
                                suggested_object_id="member_adjacency_nearest", config_entry=entry)

    entities.append(NearestDistanceSensor(coord, entry, unique_suffix="nearest_distance"))
    entities.append(NearestTargetSensor(coord, entry, unique_suffix="nearest_target"))

    # per-target sensors
    for t in coord.targets:
        oid = _obj_id(t)

        ent_reg.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_{oid}_distance",
                                    suggested_object_id=f"member_adjacency_{oid}", config_entry=entry)
        ent_reg.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_{oid}_bearing",
                                    suggested_object_id=f"member_adjacency_{oid}_bearing", config_entry=entry)
        ent_reg.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_{oid}_bucket",
                                    suggested_object_id=f"member_adjacency_{oid}_bucket", config_entry=entry)

        entities.append(PairDistanceSensor(coord, entry, target=t, unique_suffix=f"{oid}_distance"))
        entities.append(PairBearingSensor(coord, entry, target=t, unique_suffix=f"{oid}_bearing"))
        entities.append(PairBucketSensor(coord, entry, target=t, unique_suffix=f"{oid}_bucket"))

    async_add_entities(entities)


class _Base(CoordinatorEntity[MemberAdjacencyCoordinator], SensorEntity):
    _attr_should_poll = False

    def __init__(self, coord: MemberAdjacencyCoordinator, entry: ConfigEntry, *, unique_suffix: str) -> None:
        super().__init__(coord)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_state_class = SensorStateClass.MEASUREMENT


class NearestDistanceSensor(_Base):
    _attr_device_class = SensorDeviceClass.DISTANCE

    def __init__(self, coord: MemberAdjacencyCoordinator, entry: ConfigEntry, *, unique_suffix: str) -> None:
        super().__init__(coord, entry, unique_suffix=unique_suffix)
        self._attr_name = f"{DEFAULT_NAME_KO} 최근접 거리"

    @property
    def native_unit_of_measurement(self) -> str | None:
        data = self.coordinator.data
        if data.force_meters:
            return UnitOfLength.METERS
        # auto: km if >= 1000m
        if data.nearest_distance_m is not None and data.nearest_distance_m >= 1000:
            return UnitOfLength.KILOMETERS
        return UnitOfLength.METERS

    @property
    def native_value(self) -> int | float | None:
        data = self.coordinator.data
        d = data.nearest_distance_m
        if d is None:
            return None
        if data.force_meters:
            return int(round(d))
        if d >= 1000:
            return round(d / 1000.0, 2)
        return int(round(d))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        d = data.nearest_distance_m
        return {
            "anchor": data.anchor,
            "nearest_target": data.nearest_target,
            "distance_m": None if d is None else int(round(d)),
            "distance_km": None if d is None else round(d / 1000.0, 3),
            "any_proximity": data.any_proximity,
        }


class NearestTargetSensor(CoordinatorEntity[MemberAdjacencyCoordinator], SensorEntity):
    _attr_should_poll = False

    def __init__(self, coord: MemberAdjacencyCoordinator, entry: ConfigEntry, *, unique_suffix: str) -> None:
        super().__init__(coord)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_name = f"{DEFAULT_NAME_KO} 최근접 대상"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.nearest_target

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        d = data.nearest_distance_m
        return {
            "anchor": data.anchor,
            "targets": data.targets,
            "nearest_distance_m": None if d is None else int(round(d)),
            "any_proximity": data.any_proximity,
        }


class PairDistanceSensor(_Base):
    _attr_device_class = SensorDeviceClass.DISTANCE

    def __init__(self, coord: MemberAdjacencyCoordinator, entry: ConfigEntry, *, target: str, unique_suffix: str) -> None:
        super().__init__(coord, entry, unique_suffix=unique_suffix)
        self._target = target
        self._attr_name = f"{DEFAULT_NAME_KO} {target} 거리"

    @property
    def native_unit_of_measurement(self) -> str | None:
        data = self.coordinator.data
        pd = data.pairs.get(self._target)
        if data.force_meters:
            return UnitOfLength.METERS
        if pd and pd.distance_m is not None and pd.distance_m >= 1000:
            return UnitOfLength.KILOMETERS
        return UnitOfLength.METERS

    @property
    def native_value(self) -> int | float | None:
        data = self.coordinator.data
        pd = data.pairs.get(self._target)
        if not pd or pd.distance_m is None:
            return None
        d = pd.distance_m
        if data.force_meters:
            return int(round(d))
        if d >= 1000:
            return round(d / 1000.0, 2)
        return int(round(d))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        pd = data.pairs.get(self._target)
        if not pd:
            return {"anchor": data.anchor, "target": self._target}

        d = pd.distance_m
        return {
            "anchor": data.anchor,
            "target": self._target,
            "distance_m": None if d is None else int(round(d)),
            "distance_km": None if d is None else round(d / 1000.0, 3),
            "bearing_deg": pd.bearing_deg,
            "bucket": pd.bucket,
            "proximity": pd.proximity,
            "last_changed": pd.last_changed,
            "last_entered": pd.last_entered,
            "last_left": pd.last_left,
        }


class PairBearingSensor(_Base):
    def __init__(self, coord: MemberAdjacencyCoordinator, entry: ConfigEntry, *, target: str, unique_suffix: str) -> None:
        super().__init__(coord, entry, unique_suffix=unique_suffix)
        self._target = target
        self._attr_name = f"{DEFAULT_NAME_KO} {target} 방위각"
        self._attr_native_unit_of_measurement = "°"

    @property
    def native_value(self) -> int | None:
        pd = self.coordinator.data.pairs.get(self._target)
        return None if not pd else pd.bearing_deg


class PairBucketSensor(CoordinatorEntity[MemberAdjacencyCoordinator], SensorEntity):
    _attr_should_poll = False

    def __init__(self, coord: MemberAdjacencyCoordinator, entry: ConfigEntry, *, target: str, unique_suffix: str) -> None:
        super().__init__(coord)
        self._target = target
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_name = f"{DEFAULT_NAME_KO} {target} 구간"

    @property
    def native_value(self) -> str | None:
        pd = self.coordinator.data.pairs.get(self._target)
        return None if not pd else pd.bucket
