from __future__ import annotations

DOMAIN = "member_adjacency"
PLATFORMS: list[str] = ["sensor"]

CONF_ENTITY_A = "entity_a"
CONF_ENTITY_B = "entity_b"
CONF_PROXIMITY_THRESHOLD_M = "proximity_threshold_m"

DEFAULT_NAME_KO = "인접센서"
DEFAULT_ICON = "mdi:map-marker-distance"
DEFAULT_PROXIMITY_THRESHOLD_M = 500

# Only show these by default in selectors
GEO_SUFFIX = "_geocoded_location"
