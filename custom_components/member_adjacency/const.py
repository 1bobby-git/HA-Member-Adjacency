"""
Constants used by the Member Adjacency component.

This module defines keys and defaults used to configure the component.  In
addition to the original options controlling entry/exit thresholds and
accuracy filtering, several new options are provided for filtering
unrealistic movement and handling delayed location updates.  See
``manager.py`` for details on how these values are used.
"""

from __future__ import annotations

# Domain and supported platforms
DOMAIN = "member_adjacency"
PLATFORMS: list[str] = ["sensor", "binary_sensor", "button"]

# Configuration keys
CONF_ENTITY_A = "entity_a"
CONF_ENTITY_B = "entity_b"

# New semantic naming (기준점/추적대상)
CONF_BASE_ENTITY = "base_entity"
CONF_TRACKER_ENTITY = "tracker_entity"

CONF_ENTRY_THRESHOLD_M = "entry_threshold_m"
CONF_EXIT_THRESHOLD_M = "exit_threshold_m"
CONF_DEBOUNCE_SECONDS = "debounce_seconds"
CONF_MAX_ACCURACY_M = "max_accuracy_m"
CONF_FORCE_METERS = "force_meters"

# New configuration keys for movement filtering and resync handling
CONF_RESYNC_SILENCE_S = "resync_silence_s"  # seconds of silence to trigger resync
CONF_RESYNC_HOLD_S = "resync_hold_s"        # seconds to ignore updates after resync
CONF_MAX_SPEED_KMH = "max_speed_kmh"        # max reasonable speed before filtering
CONF_MIN_UPDATES_FOR_PROXIMITY = "min_updates_for_proximity"  # min updates in window for valid proximity
CONF_UPDATE_WINDOW_S = "update_window_s"    # window for counting recent updates
CONF_REQUIRE_RELIABLE_PROXIMITY = "require_reliable_proximity"  # require reliable data for enter event

# Defaults
DEFAULT_NAME_KO = "인접센서"

DEFAULT_ENTRY_THRESHOLD_M = 500
DEFAULT_EXIT_THRESHOLD_M = 700
DEFAULT_DEBOUNCE_SECONDS = 2
DEFAULT_MAX_ACCURACY_M = 200
DEFAULT_FORCE_METERS = False

# Defaults for movement filtering
DEFAULT_RESYNC_SILENCE_S = 600  # 10 minutes of silence marks resync
DEFAULT_RESYNC_HOLD_S = 60      # ignore updates for 60 seconds after resync
DEFAULT_MAX_SPEED_KMH = 150.0    # any speed over 150 km/h is considered invalid
DEFAULT_MIN_UPDATES_FOR_PROXIMITY = 3  # both sides need at least 3 updates in window (conservative)
DEFAULT_UPDATE_WINDOW_S = 300    # 5 minute window for counting updates
DEFAULT_REQUIRE_RELIABLE_PROXIMITY = True  # safe default: only fire enter event if reliable

# Suffix for geocoded sensors
GEO_SUFFIX = "_geocoded_location"

# Bucket thresholds (meters)
BUCKETS = [
    (50, "very_near"),
    (200, "near"),
    (1000, "mid"),
    (5000, "far"),
    (10**12, "very_far"),
]

# Event names dispatched on the Home Assistant bus
EVENT_ENTER = "member_adjacency_enter"
EVENT_LEAVE = "member_adjacency_leave"
EVENT_PROXIMITY_UPDATE = "member_adjacency_proximity_update"
EVENT_ENTER_UNRELIABLE = "member_adjacency_enter_unreliable"

# Dispatcher signal prefix used by the manager to notify entities
SIGNAL_UPDATE_PREFIX = "member_adjacency_update"