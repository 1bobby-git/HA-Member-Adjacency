from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, DEFAULT_NAME_KO
from .manager import AdjacencyManager


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    mgr: AdjacencyManager = hass.data[DOMAIN][entry.entry_id]

    ent_reg = er.async_get(hass)
    pair_key = mgr.pair_key

    ent_reg.async_get_or_create(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_proximity",
        suggested_object_id=f"member_adjacency_{pair_key}_proximity",
        config_entry=entry,
    )

    async_add_entities([MemberAdjacencyProximityBinary(mgr)])


class MemberAdjacencyProximityBinary(BinarySensorEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:map-marker-circle"

    def __init__(self, mgr: AdjacencyManager) -> None:
        self.mgr = mgr
        self._attr_unique_id = f"{mgr.entry.entry_id}_proximity"
        self._attr_name = f"{DEFAULT_NAME_KO} 근접"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        @callback
        def _updated() -> None:
            self.async_write_ha_state()

        self._unsub = async_dispatcher_connect(self.hass, self.mgr.signal, _updated)
        self.async_on_remove(self._unsub)

    @property
    def device_info(self):
        return self.mgr.device_info()

    @property
    def is_on(self) -> bool:
        return bool(self.mgr.data.proximity)

    @property
    def extra_state_attributes(self):
        return {
            "entity_a": self.mgr.entity_a,
            "entity_b": self.mgr.entity_b,
            "entry_threshold_m": self.mgr.entry_th,
            "exit_threshold_m": self.mgr.exit_th,
            "data_valid": self.mgr.data.data_valid,
            "last_valid_updated": self.mgr.data.last_valid_updated,
            "last_error": self.mgr.data.last_error,
            "last_changed": self.mgr.data.last_changed,
            "last_entered": self.mgr.data.last_entered,
            "last_left": self.mgr.data.last_left,
        }
