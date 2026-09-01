"""
Binary sensor platform for the Member Adjacency component.

The binary sensor reports the reliable proximity state. When either source
location is missing or rejected by an accuracy/movement filter, Home Assistant
marks the entity unavailable instead of exposing a stale on/off value.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .manager import AdjacencyManager


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    """Set up the Member Adjacency binary sensor for a config entry."""
    manager: AdjacencyManager = hass.data[DOMAIN][entry.entry_id]

    entity_registry = er.async_get(hass)
    pair_key = manager.pair_key

    entity_registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_proximity",
        suggested_object_id=f"member_adjacency_{pair_key}_proximity",
        config_entry=entry,
    )

    async_add_entities([MemberAdjacencyProximityBinary(manager)])


class MemberAdjacencyProximityBinary(BinarySensorEntity):
    """Binary sensor indicating reliable proximity between two entities."""

    _attr_should_poll = False
    _attr_icon = "mdi:map-marker-circle"

    def __init__(self, manager: AdjacencyManager) -> None:
        self.mgr = manager
        self._attr_unique_id = f"{manager.entry.entry_id}_proximity"
        self._attr_name = (
            f"{manager.get_tracker_name()} → {manager.get_base_name()} 근접"
        )
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
    def available(self) -> bool:
        """Return false while the current source sample is invalid."""
        return self.mgr.data.data_valid

    @property
    def is_on(self) -> bool:
        return bool(self.mgr.data.proximity)

    @property
    def extra_state_attributes(self):
        return {
            "base_entity": self.mgr.base_entity,
            "tracker_entity": self.mgr.tracker_entity,
            "base_speed_kmh": (
                None
                if self.mgr.a_speed_kmh is None
                else round(self.mgr.a_speed_kmh, 1)
            ),
            "tracker_speed_kmh": (
                None
                if self.mgr.b_speed_kmh is None
                else round(self.mgr.b_speed_kmh, 1)
            ),
            "base_last_update": (
                self.mgr.a_last_fix.isoformat() if self.mgr.a_last_fix else None
            ),
            "tracker_last_update": (
                self.mgr.b_last_fix.isoformat() if self.mgr.b_last_fix else None
            ),
            "base_updates_recent": self.mgr.data.a_updates_in_window,
            "tracker_updates_recent": self.mgr.data.b_updates_in_window,
            "raw_proximity": bool(
                getattr(self.mgr.data, "raw_proximity", self.mgr.data.proximity)
            ),
            "entity_a": self.mgr.base_entity,
            "entity_b": self.mgr.tracker_entity,
            "speed_a_kmh": (
                None
                if self.mgr.a_speed_kmh is None
                else round(self.mgr.a_speed_kmh, 1)
            ),
            "speed_b_kmh": (
                None
                if self.mgr.b_speed_kmh is None
                else round(self.mgr.b_speed_kmh, 1)
            ),
            "a_last_fix": (
                self.mgr.a_last_fix.isoformat() if self.mgr.a_last_fix else None
            ),
            "b_last_fix": (
                self.mgr.b_last_fix.isoformat() if self.mgr.b_last_fix else None
            ),
            "a_resync_until": (
                self.mgr.a_resync_until.isoformat()
                if self.mgr.a_resync_until
                else None
            ),
            "b_resync_until": (
                self.mgr.b_resync_until.isoformat()
                if self.mgr.b_resync_until
                else None
            ),
            "a_updates_in_window": self.mgr.data.a_updates_in_window,
            "b_updates_in_window": self.mgr.data.b_updates_in_window,
            "entry_threshold_m": self.mgr.entry_th,
            "exit_threshold_m": self.mgr.exit_th,
            "debounce_seconds": self.mgr.debounce_s,
            "max_accuracy_m": self.mgr.max_acc_m,
            "force_meters": self.mgr.force_meters,
            "resync_silence_s": self.mgr.resync_silence_s,
            "resync_hold_s": self.mgr.resync_hold_s,
            "max_speed_kmh": self.mgr.max_speed_kmh,
            "min_updates_for_proximity": self.mgr.min_updates_for_proximity,
            "update_window_s": self.mgr.update_window_s,
            "require_reliable_proximity": self.mgr.require_reliable_proximity,
            "data_valid": self.mgr.data.data_valid,
            "last_valid_updated": self.mgr.data.last_valid_updated,
            "last_error": self.mgr.data.last_error,
            "proximity_update_count": self.mgr.data.proximity_update_count,
            "proximity_duration_min": self.mgr.proximity_duration_minutes(),
            "proximity_duration_human": self.mgr.proximity_duration_human(),
            "last_changed": self.mgr.data.last_changed,
            "last_entered": self.mgr.data.last_entered,
            "last_left": self.mgr.data.last_left,
            "proximity_reliable": self.mgr.data.proximity_reliable,
            "unreliable_reason": self.mgr.data.unreliable_reason,
            "convergence_speed_kmh": (
                None
                if self.mgr.data.convergence_speed_kmh is None
                else round(self.mgr.data.convergence_speed_kmh, 1)
            ),
        }
