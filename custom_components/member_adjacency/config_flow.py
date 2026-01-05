from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_SECONDS,
    CONF_MAX_ACCURACY_M,
    CONF_FORCE_METERS,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_FORCE_METERS,
    DOMAIN,
    GEO_SUFFIX,
)


def _try_get_coords_from_state(state) -> tuple[float, float] | None:
    if state is None:
        return None
    attrs = state.attributes or {}

    loc = attrs.get("Location")
    if isinstance(loc, (list, tuple)) and len(loc) == 2:
        try:
            return (float(loc[0]), float(loc[1]))
        except (TypeError, ValueError):
            return None

    if "latitude" in attrs and "longitude" in attrs:
        try:
            return (float(attrs["latitude"]), float(attrs["longitude"]))
        except (TypeError, ValueError):
            return None

    if isinstance(state.state, str) and "," in state.state:
        parts = [p.strip() for p in state.state.split(",")]
        if len(parts) == 2:
            try:
                return (float(parts[0]), float(parts[1]))
            except (TypeError, ValueError):
                return None

    return None


def _device_name_for_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    ent = ent_reg.async_get(entity_id)
    if ent and ent.device_id:
        dev = dev_reg.async_get(ent.device_id)
        if dev:
            return dev.name_by_user or dev.name
    return None


def _label_for_entity(hass: HomeAssistant, entity_id: str) -> str:
    dev_name = _device_name_for_entity(hass, entity_id)
    if dev_name:
        return f"{dev_name} ({entity_id})"

    st = hass.states.get(entity_id)
    fn = None if st is None else (st.attributes or {}).get("friendly_name")
    if fn:
        return f"{fn} ({entity_id})"

    return entity_id


def _candidate_entities(hass: HomeAssistant) -> list[str]:
    """
    셀렉트 박스에 노출할 엔티티 목록:
    - sensor.*_geocoded_location: coords가 실제로 존재하는 것만 노출
    - person.*, device_tracker.*, sensor.*: coords가 있는 것만 노출
    - zone 제외
    """
    out: list[str] = []

    # 1) geocoded sensors (coords 있는 것만)
    for st in hass.states.async_all("sensor"):
        if not st.entity_id.endswith(GEO_SUFFIX):
            continue
        if st.state in ("unknown", "unavailable"):
            continue
        if _try_get_coords_from_state(st) is not None:
            out.append(st.entity_id)

    # 2) person/device_tracker + other sensors (coords 있는 것만)
    for domain in ("person", "device_tracker", "sensor"):
        for st in hass.states.async_all(domain):
            if st.entity_id.startswith("zone."):
                continue
            if st.entity_id in out:
                continue
            if st.state in ("unknown", "unavailable"):
                continue
            if _try_get_coords_from_state(st) is not None:
                out.append(st.entity_id)

    out = sorted(set(out))
    return out


class MemberAdjacencyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        candidates = _candidate_entities(self.hass)
        default_a = candidates[0] if len(candidates) >= 1 else None
        default_b = candidates[1] if len(candidates) >= 2 else None

        if user_input is not None:
            a = user_input[CONF_ENTITY_A]
            b = user_input[CONF_ENTITY_B]

            if a.startswith("zone.") or b.startswith("zone."):
                errors["base"] = "zone_not_supported"

            if a == b:
                errors[CONF_ENTITY_B] = "same_entity"

            if not errors:
                # 강건성: 혹시나 목록 외 입력/상태 변화로 coords가 없는 경우 방지
                if _try_get_coords_from_state(self.hass.states.get(a)) is None:
                    errors[CONF_ENTITY_A] = "invalid_entity"
                if _try_get_coords_from_state(self.hass.states.get(b)) is None:
                    errors[CONF_ENTITY_B] = "invalid_entity"

            entry_th = int(user_input[CONF_ENTRY_THRESHOLD_M])
            exit_th = int(user_input[CONF_EXIT_THRESHOLD_M])
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"

            if not errors:
                pair = "__".join(sorted([a, b]))
                await self.async_set_unique_id(pair)
                self._abort_if_unique_id_configured()

                # ✅ 스샷1 요구사항: 구성요소 항목 제목을 device name 기반으로
                a_name = _device_name_for_entity(self.hass, a) or _label_for_entity(self.hass, a)
                b_name = _device_name_for_entity(self.hass, b) or _label_for_entity(self.hass, b)
                title = f"{a_name.split(' (', 1)[0]} ↔ {b_name.split(' (', 1)[0]}"

                return self.async_create_entry(title=title, data=user_input)

        # selector options with labels (value=entity_id, label="Device (entity_id)")
        options = [{"value": eid, "label": _label_for_entity(self.hass, eid)} for eid in candidates]

        if options:
            sel = selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
            entity_sel_a = selector.SelectSelector(sel)
            entity_sel_b = selector.SelectSelector(sel)
        else:
            # fallback - still excludes zone by domains
            entity_sel_a = selector.EntitySelector(
                selector.EntitySelectorConfig(include_domains=["sensor", "person", "device_tracker"])
            )
            entity_sel_b = selector.EntitySelector(
                selector.EntitySelectorConfig(include_domains=["sensor", "person", "device_tracker"])
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_A, default=default_a): entity_sel_a,
                vol.Required(CONF_ENTITY_B, default=default_b): entity_sel_b,
                vol.Required(CONF_ENTRY_THRESHOLD_M, default=DEFAULT_ENTRY_THRESHOLD_M): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Required(CONF_EXIT_THRESHOLD_M, default=DEFAULT_EXIT_THRESHOLD_M): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Optional(CONF_DEBOUNCE_SECONDS, default=DEFAULT_DEBOUNCE_SECONDS): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=60)
                ),
                vol.Optional(CONF_MAX_ACCURACY_M, default=DEFAULT_MAX_ACCURACY_M): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=10_000)
                ),
                vol.Optional(CONF_FORCE_METERS, default=DEFAULT_FORCE_METERS): bool,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MemberAdjacencyOptionsFlow(config_entry)


class MemberAdjacencyOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        data = {**self._entry.data, **self._entry.options}

        if user_input is not None:
            entry_th = int(user_input.get(CONF_ENTRY_THRESHOLD_M, data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)))
            exit_th = int(user_input.get(CONF_EXIT_THRESHOLD_M, data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)))
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(CONF_ENTRY_THRESHOLD_M, default=data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Optional(CONF_EXIT_THRESHOLD_M, default=data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Optional(CONF_DEBOUNCE_SECONDS, default=data.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=60)
                ),
                vol.Optional(CONF_MAX_ACCURACY_M, default=data.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=10_000)
                ),
                vol.Optional(CONF_FORCE_METERS, default=data.get(CONF_FORCE_METERS, DEFAULT_FORCE_METERS)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
