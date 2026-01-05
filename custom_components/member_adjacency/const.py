from __future__ import annotations

DOMAIN = "member_adjacency"
PLATFORMS: list[str] = ["sensor"]

CONF_ENTITY_A = "entity_a"
CONF_ENTITY_B = "entity_b"
CONF_NAME = "name"
CONF_ICON = "icon"
CONF_ROUNDING = "rounding"
CONF_PROXIMITY_THRESHOLD_M = "proximity_threshold_m"

DEFAULT_NAME = "인접 센서"
DEFAULT_ICON = "mdi:map-marker-distance"
DEFAULT_ROUNDING = 0
DEFAULT_PROXIMITY_THRESHOLD_M = 500
