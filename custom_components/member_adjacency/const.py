from __future__ import annotations

DOMAIN = "member_adjacency"
PLATFORMS: list[str] = ["sensor", "binary_sensor", "button"]

CONF_ENTITY_A = "entity_a"
CONF_ENTITY_B = "entity_b"

CONF_ENTRY_THRESHOLD_M = "entry_threshold_m"
CONF_EXIT_THRESHOLD_M = "exit_threshold_m"
CONF_DEBOUNCE_SECONDS = "debounce_seconds"
CONF_MAX_ACCURACY_M = "max_accuracy_m"
CONF_FORCE_METERS = "force_meters"

DEFAULT_NAME_KO = "인접센서"

DEFAULT_ENTRY_THRESHOLD_M = 500
DEFAULT_EXIT_THRESHOLD_M = 700
DEFAULT_DEBOUNCE_SECONDS = 2
DEFAULT_MAX_ACCURACY_M = 200
DEFAULT_FORCE_METERS = False

GEO_SUFFIX = "_geocoded_location"

# bucket thresholds (meters)
BUCKETS = [
    (50, "very_near"),
    (200, "near"),
    (1000, "mid"),
    (5000, "far"),
    (10**12, "very_far"),
]

EVENT_ENTER = "member_adjacency_enter"
EVENT_LEAVE = "member_adjacency_leave"
EVENT_PROXIMITY_UPDATE = "member_adjacency_proximity_update"

SIGNAL_UPDATE_PREFIX = "member_adjacency_update"
