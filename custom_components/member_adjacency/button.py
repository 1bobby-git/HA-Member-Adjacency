from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, DEFAULT_NAME_KO
from .manager import AdjacencyManager


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    mgr: AdjacencyManager = hass.data[DOMAIN][entry.entry_id]

    ent_reg = er.async_get(hass)
    pair_key = mgr.pair_key

    ent_reg.async_get_or_create(
        "button", DOMAIN, f"{entry.entry_id}_refresh",
        suggested_object_id=f"member_adjacency_{pair_key}_refresh",
        config_entry=entry,
    )

    async_add_entities([MemberAdjacencyRefreshButton(mgr)])


class MemberAdjacencyRefreshButton(ButtonEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:refresh"

    def __init__(self, mgr: AdjacencyManager) -> None:
        self.mgr = mgr
        self._attr_unique_id = f"{mgr.entry.entry_id}_refresh"
        self._attr_name = f"{DEFAULT_NAME_KO} 새로고침"

    @property
    def device_info(self):
        return self.mgr.device_info()

    async def async_press(self) -> None:
        await self.mgr.async_force_refresh_with_source_update()
