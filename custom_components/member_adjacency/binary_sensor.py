from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
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

    entities: list[BinarySensorEntity] = []

    # any proximity
    ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_any_proximity",
        suggested_object_id="member_adjacency_proximity",
        config_entry=entry,
    )
    entities.append(AnyProximityBinary(coord, entry, unique_suffix="any_proximity"))

    # per-target proximity
    for t in coord.targets:
        oid = _obj_id(t)
        ent_reg.async_get_or_create(
            "binary_sensor",
            DOMAIN,
            f"{entry.entry_id}_{oid}_proximity",
            suggested_object_id=f"member_adjacency_{oid}_proximity",
            config_entry=entry,
        )
        entities.append(PairProximityBinary(coord, entry, target=t, unique_suffix=f"{oid}_proximity"))

    async_add_entities(entities)


class AnyProximityBinary(CoordinatorEntity[MemberAdjacencyCoordinator], BinarySensorEntity):
    _attr_should_poll = False

    def __init__(self, coord: MemberAdjacencyCoordinator, entry: ConfigEntry, *, unique_suffix: str) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_name = f"{DEFAULT_NAME_KO} 전체 근접"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.any_proximity


class PairProximityBinary(CoordinatorEntity[MemberAdjacencyCoordinator], BinarySensorEntity):
    _attr_should_poll = False

    def __init__(self, coord: MemberAdjacencyCoordinator, entry: ConfigEntry, *, target: str, unique_suffix: str) -> None:
        super().__init__(coord)
        self._target = target
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_name = f"{DEFAULT_NAME_KO} {target} 근접"

    @property
    def is_on(self) -> bool:
        pd = self.coordinator.data.pairs.get(self._target)
        return bool(pd and pd.proximity)

    @property
    def extra_state_attributes(self):
        pd = self.coordinator.data.pairs.get(self._target)
        if not pd:
            return {"target": self._target}
        return {
            "target": self._target,
            "last_changed": pd.last_changed,
            "last_entered": pd.last_entered,
            "last_left": pd.last_left,
        }
