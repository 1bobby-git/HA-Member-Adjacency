from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, DEFAULT_NAME_KO
from .sensor import _short, _get, CONF_ENTITY_A, CONF_ENTITY_B, _obj_id  # reuse helpers


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    a = _get(entry, CONF_ENTITY_A, "")
    b = _get(entry, CONF_ENTITY_B, "")

    a_id = _short(a)
    b_id = _short(b)
    pair_key = f"{a_id}_{b_id}" if a_id and b_id else entry.entry_id

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_proximity",
        suggested_object_id=f"member_adjacency_{pair_key}_proximity",
        config_entry=entry,
    )

    async_add_entities([MemberAdjacencyProximityBinary(hass, entry)])


class MemberAdjacencyProximityBinary(BinarySensorEntity):
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.entity_a = _get(entry, CONF_ENTITY_A, "")
        self.entity_b = _get(entry, CONF_ENTITY_B, "")

        self._attr_unique_id = f"{entry.entry_id}_proximity"
        self._attr_name = f"{DEFAULT_NAME_KO} {_short(self.entity_a)}↔{_short(self.entity_b)} 근접"

    @property
    def is_on(self) -> bool:
        # proximity는 distance 센서가 계산해 attributes에 넣고 있으므로 그 값을 읽어온다.
        # (동일 entry_id 기반으로 sensor unique_id가 고정이라, entity_id는 레지스트리 상황에 따라 다를 수 있음)
        # 안정적으로는 동일 기기(통합) 내 센서 중 distance 센서의 attributes를 읽는게 가장 단순함.
        # 여기서는 이름 기반 탐색 대신, entity_registry에서 이 entry의 distance 센서를 찾는다.
        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(self.hass)
        # platform = sensor, unique_id suffix = _distance
        ent = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{self.entry.entry_id}_distance")
        if not ent:
            return False

        st = self.hass.states.get(ent)
        if not st:
            return False

        return bool((st.attributes or {}).get("proximity", False))
