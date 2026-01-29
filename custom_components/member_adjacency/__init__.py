"""
Home Assistant integration entry point for the Member Adjacency component.

This module creates a new :class:`AdjacencyManager` for each config entry
and forwards setup/unload calls to the appropriate platform modules.  The
manager handles all of the core distance/proximity computations so that
sensor, binary_sensor and button platforms can stay simple.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .manager import AdjacencyManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Member Adjacency entry.

    A new :class:`AdjacencyManager` is created and stored under
    ``hass.data[DOMAIN]`` keyed by the entry ID.  The manager is
    responsible for computing distances, tracking proximity state and
    exposing convenience properties used by entities.  Once started the
    platforms are forwarded to register their entities.
    """
    mgr = AdjacencyManager(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mgr
    await mgr.async_start()
    # Forward setup to the individual platforms (sensor, binary_sensor, button)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Member Adjacency entry.

    This tears down the platforms and stops the manager.  After a successful
    unload the manager is removed from ``hass.data``.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        mgr: AdjacencyManager | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if mgr:
            await mgr.async_stop()
    return unload_ok