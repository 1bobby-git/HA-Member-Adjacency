from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import (
    CONF_ANCHOR,
    CONF_TARGETS,
    CONF_PRESET,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_SECONDS,
    CONF_MAX_ACCURACY_M,
    CONF_FORCE_METERS,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_FORCE_METERS,
    DOMAIN,
    GEO_SUFFIX,
    PRESET_OPTIONS,
)


def _geocoded_candidates(hass: HomeAssistant) -> list[str]:
    out: list[str] = []
    for st in hass.states.async_all("sensor"):
        if st.entity_id.endswith(GEO_SUFFIX):
            out.append(st.entity_id)
    out.sort()
    return out


def _default_targets(candidates: list[str], anchor: str | None) -> list[str]:
    if not candidates:
        return []
    c = [x for x in candidates if x != anchor]
    return c[:2]


class MemberAdjacencyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        candidates = _geocoded_candidates(self.hass)

        default_anchor = candidates[0] if candidates else None
        default_targets = _default_targets(candidates, default_anchor)

        if user_input is not None:
            anchor = user_input[CONF_ANCHOR]
            targets = user_input[CONF_TARGETS]

            if not anchor.endswith(GEO_SUFFIX):
                errors[CONF_ANCHOR] = "not_geocoded"
            if any(not t.endswith(GEO_SUFFIX) for t in targets):
                errors[CONF_TARGETS] = "not_geocoded"

            if anchor in targets:
                errors[CONF_TARGETS] = "targets_contains_anchor"

            if not targets:
                errors[CONF_TARGETS] = "targets_empty"

            # preset -> entry default handling
            preset = user_input.get(CONF_PRESET, "custom")
            if preset in PRESET_OPTIONS and PRESET_OPTIONS[preset] is not None:
                user_input[CONF_ENTRY_THRESHOLD_M] = PRESET_OPTIONS[preset]
                # keep exit at least entry + 200
                user_input[CONF_EXIT_THRESHOLD_M] = max(
                    user_input.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M),
                    PRESET_OPTIONS[preset] + 200,
                )

            entry_th = int(user_input[CONF_ENTRY_THRESHOLD_M])
            exit_th = int(user_input[CONF_EXIT_THRESHOLD_M])
            if exit_th < entry_th:
                errors[CONF_EXIT_THRESHOLD_M] = "exit_lt_entry"

            if not errors:
                # unique id: anchor + sorted targets
                uniq = "__".join([anchor] + sorted(targets))
                await self.async_set_unique_id(uniq)
                self._abort_if_unique_id_configured()

                title = f"{anchor} ↔ {len(targets)} targets"
                # store preset only for UX; actual thresholds stored too
                return self.async_create_entry(title=title, data=user_input)

        if candidates:
            anchor_sel = selector.SelectSelector(
                selector.SelectSelectorConfig(options=candidates, mode=selector.SelectSelectorMode.DROPDOWN)
            )
            targets_sel = selector.SelectSelector(
                selector.SelectSelectorConfig(options=candidates, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        else:
            # fallback (no geocoded sensors found)
            anchor_sel = selector.EntitySelector()
            targets_sel = selector.EntitySelector()

        preset_sel = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(PRESET_OPTIONS.keys()),
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_ANCHOR, default=default_anchor): anchor_sel,
                vol.Required(CONF_TARGETS, default=default_targets): targets_sel,
                vol.Optional(CONF_PRESET, default="500"): preset_sel,
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

        preset_sel = selector.SelectSelector(
            selector.SelectSelectorConfig(options=list(PRESET_OPTIONS.keys()), mode=selector.SelectSelectorMode.DROPDOWN)
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_PRESET, default=data.get(CONF_PRESET, "custom")): preset_sel,
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
