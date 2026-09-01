"""
Home Assistant integration entry point for the Member Adjacency component.

This module creates a new :class:`AdjacencyManager` for each config entry
and forwards setup/unload calls to the appropriate platform modules. The
manager handles all distance and reliable-proximity computations so that
sensor, binary_sensor and button platforms can stay simple.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_BASE_ENTITY,
    CONF_TRACKER_ENTITY,
)
from .runtime_manager import AdjacencyManager


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry to new format."""
    if entry.version == 1:
        new_data = dict(entry.data)

        if CONF_ENTITY_A in new_data and CONF_BASE_ENTITY not in new_data:
            new_data[CONF_BASE_ENTITY] = new_data[CONF_ENTITY_A]

        if CONF_ENTITY_B in new_data and CONF_TRACKER_ENTITY not in new_data:
            new_data[CONF_TRACKER_ENTITY] = new_data[CONF_ENTITY_B]

        hass.config_entries.async_update_entry(entry, data=new_data, version=2)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Member Adjacency entry."""
    manager = AdjacencyManager(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await manager.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Member Adjacency entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        manager: AdjacencyManager | None = hass.data.get(DOMAIN, {}).pop(
            entry.entry_id,
            None,
        )
        if manager:
            await manager.async_stop()
    return unload_ok
