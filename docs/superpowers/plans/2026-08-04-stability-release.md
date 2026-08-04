# HA-Member-Adjacency Diagnostics and v1.6.0 Release Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Goal
- Add non-disruptive failure diagnostics logging in `AdjacencyManager.async_request_source_update`.
- Keep movement and proximity core paths behavior-stable while making failure paths observable.
- Ensure `manifest.json` version (`1.6.0`) is aligned with git tags and GitHub release artifacts.
- Separate normal PR/push checks from release checks so missing tags do not block regular CI.

## Architecture
- `manager.py`: movement vector calculation, movement filtering, proximity reliability checks, resync gating, and failure logging.
- `config_flow.py`, `__init__.py`: preserve current flow and keep option injection via `entry.data` / `entry.options`.
- `sensor.py`, `binary_sensor.py`, `button.py`: keep dispatcher/event behavior unchanged.
- `Async refresh` and service-call retry behavior remain functional and only gain additional diagnostic traces.

## Tech Stack
- Python 3.12
- Home Assistant Core integration framework
- pytest, pytest-asyncio, pytest-caplog
- GitHub CLI (`gh`) + git

---

## Symbol mapping (exact)
- `custom_components/member_adjacency/manager.py`
  - `AdjacencyManager`
  - `async_request_source_update(self, entity_id: str) -> None`
  - `_mobile_app_identifier_from_entity(self, entity_id: str) -> str | None`
  - `_update_movement(self, coords_a: tuple[float, float] | None, coords_b: tuple[float, float] | None) -> str | None`
  - `_check_proximity_reliability(self, current_distance_m: float) -> tuple[bool, str | None]`
  - `async_refresh(self) -> None`
- `custom_components/member_adjacency/const.py`
  - `CONF_RESYNC_SILENCE_S`, `CONF_RESYNC_HOLD_S`, `CONF_MAX_SPEED_KMH`, `CONF_MIN_UPDATES_FOR_PROXIMITY`, `CONF_UPDATE_WINDOW_S`, `CONF_REQUIRE_RELIABLE_PROXIMITY`
- `custom_components/member_adjacency/manifest.json`
  - `version`
- `.github/workflows/validate.yaml`

## Task 1 (2~5 minutes): Add failure diagnostics logging
- Files
  - `custom_components/member_adjacency/manager.py`
  - `custom_components/member_adjacency/manager.py:392-437`
- Checklist
  - [ ] `notify` failure logs use `self.hass.logger.debug`
  - [ ] `update_entity` failure logs use `self.hass.logger.debug`
  - [ ] logs include `entity_id`, `service`, `exception_type`, `exception_msg`
  - [ ] button/click/manual refresh behavior is unchanged
- Example implementation
```python
from typing import Any


def _log_failure(self, message: str, *, entity_id: str, service: str | None = None, error: Exception | None = None) -> None:
    if error is not None:
        payload: dict[str, Any] = {
            "entity_id": entity_id,
            "exception_type": type(error).__name__,
            "exception_msg": str(error),
        }
    else:
        payload = {"entity_id": entity_id}
    if service is not None:
        payload["service"] = service
    self.hass.logger.debug(message, extra=payload)


async def async_request_source_update(self, entity_id: str) -> None:
    if not entity_id or entity_id.startswith("zone."):
        return

    mobile_id = self._mobile_app_identifier_from_entity(entity_id)
    if mobile_id:
        service = f"mobile_app_{_sanitize_service_suffix(mobile_id)}"
        if self.hass.services.has_service("notify", service):
            try:
                await self.hass.services.async_call(
                    "notify", service, {"message": "request_location_update"}, blocking=True
                )
                await asyncio.sleep(0.3)
            except Exception as err:
                self._log_failure(
                    "member_adjacency.request_location_update_failed",
                    entity_id=entity_id,
                    service=service,
                    error=err,
                )

    if self.hass.services.has_service("homeassistant", "update_entity"):
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "update_entity",
                {"entity_id": entity_id},
                blocking=True,
            )
        except Exception as err:
            self._log_failure(
                "member_adjacency.update_entity_failed",
                entity_id=entity_id,
                error=err,
            )
```
- Commands
  - `python -m compileall custom_components/member_adjacency/manager.py`
- Expected
  - Red: debug logs are missing on failure paths
  - Green: at least one failure path logs DEBUG with required fields

## Task 2 (2~5 minutes): Add caplog-based async_request_source_update tests
- Files
  - `tests/components/member_adjacency/test_manager.py`
  - `tests/components/member_adjacency/conftest.py`
- Checklist
  - [ ] notify failure emits debug log via caplog
  - [ ] update_entity failure emits debug log via caplog
  - [ ] message, level, and fields are asserted
- Example tests
```python
import pytest
from unittest.mock import AsyncMock, Mock

from custom_components.member_adjacency.manager import AdjacencyManager


@pytest.mark.asyncio
async def test_async_request_source_update_logs_notify_failure(caplog, hass, manager_entry):
    manager = AdjacencyManager(hass, manager_entry)
    manager._mobile_app_identifier_from_entity = Mock(return_value="phone_abc")
    hass.services.has_service = Mock(return_value=True)
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("notify denied"))

    with caplog.at_level("DEBUG"):
        await manager.async_request_source_update("person.test")

    assert any(
        rec.message == "member_adjacency.request_location_update_failed"
        and rec.levelname == "DEBUG"
        and rec.__dict__.get("entity_id") == "person.test"
        and rec.__dict__.get("service") == "mobile_app_phone_abc"
        and rec.__dict__.get("exception_type") == "RuntimeError"
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_async_request_source_update_logs_update_entity_failure(caplog, hass, manager_entry):
    manager = AdjacencyManager(hass, manager_entry)
    manager._mobile_app_identifier_from_entity = Mock(return_value=None)

    async def async_call(domain, service, data=None, blocking=False):
        if domain == "homeassistant" and service == "update_entity":
            raise RuntimeError("update denied")
        return None

    hass.services.has_service = Mock(
        side_effect=lambda d, s: d == "homeassistant" and s == "update_entity"
    )
    hass.services.async_call = async_call

    with caplog.at_level("DEBUG"):
        await manager.async_request_source_update("person.test")

    assert any(
        rec.message == "member_adjacency.update_entity_failed"
        and rec.levelname == "DEBUG"
        and rec.__dict__.get("entity_id") == "person.test"
        and rec.__dict__.get("exception_type") == "RuntimeError"
        for rec in caplog.records
    )
```
- Commands
  - `pytest tests/components/member_adjacency/test_manager.py -k "request_source_update"`
- Expected
  - Red: assertions fail on message/level/field formatting
  - Green: both tests pass and emit expected debug records

## Task 3 (2~5 minutes): manager movement and reliability logic tests
- Files
  - `tests/components/member_adjacency/test_manager.py`
  - `custom_components/member_adjacency/manager.py`
- Checklist
  - [ ] `_update_movement` speed-filter branch is validated
  - [ ] `_check_proximity_reliability` detects insufficient update history
  - [ ] unrealistic convergence is rejected with a clear reason
  - [ ] `resync` gating is validated with required update history
  - [ ] `async_refresh` event path remains stable
  - [ ] no regression in state transitions
- Example tests
```python
import datetime as dt
from unittest.mock import Mock

import pytest
from freezegun import freeze_time

from custom_components.member_adjacency.manager import AdjacencyManager
from homeassistant.util import dt as dt_util


@pytest.mark.usefixtures("hass")
def test_update_movement_speed_filter_blocked_by_limit(hass, manager_entry):
    mgr = AdjacencyManager(hass, manager_entry)
    mgr.max_speed_kmh = 1
    now = dt.datetime(2026, 8, 4, tzinfo=dt.timezone.utc)
    dt_util.utcnow = Mock(return_value=now)

    mgr.a_last_fix = now - dt.timedelta(minutes=10)
    mgr.b_last_fix = now - dt.timedelta(minutes=10)
    mgr.a_prev_coords = (37.0, 127.0)
    mgr.b_prev_coords = (37.0, 127.0)

    result = mgr._update_movement((39.0, 130.0), (37.0, 127.0))
    assert result == "speed_filtered_a"


def test_check_proximity_reliability_rejects_missing_updates(hass, manager_entry):
    mgr = AdjacencyManager(hass, manager_entry)
    mgr.min_updates_for_proximity = 3
    mgr.update_window_s = 300
    mgr.a_update_history = []
    mgr.b_update_history = []
    reliable, reason = mgr._check_proximity_reliability(50.0)
    assert reliable is False
    assert reason == "insufficient_updates_a (0<3)"


def test_check_proximity_reliability_rejects_unreliable_convergence(hass, manager_entry):
    mgr = AdjacencyManager(hass, manager_entry)
    mgr._prev_distance_m = 20000.0
    mgr._prev_distance_time = dt_util.utcnow()
    mgr.max_speed_kmh = 10
    mgr.a_update_history = [dt_util.utcnow() - dt.timedelta(seconds=10)]
    mgr.b_update_history = [dt_util.utcnow() - dt.timedelta(seconds=10)]
    reliable, reason = mgr._check_proximity_reliability(0.0)
    assert reliable is False
    assert reason.startswith("unrealistic_convergence (")


def test_require_reliable_blocks_enter_event_path(monkeypatch, hass, manager_entry):
    mgr = AdjacencyManager(hass, manager_entry)
    mgr.require_reliable_proximity = True
    mgr.max_speed_kmh = 9999
    mgr.min_updates_for_proximity = 3
    mgr.update_window_s = 300
    now = dt_util.utcnow()
    mgr.a_update_history = [now - dt.timedelta(seconds=10)] * 3
    mgr.b_update_history = [now - dt.timedelta(seconds=10)] * 3
    mgr._prev_distance_m = 200
    mgr._prev_distance_time = now - dt.timedelta(seconds=120)
    reliability, reason = mgr._check_proximity_reliability(50.0)
    assert reliability is True
    assert reason is None
```
- Commands
  - `pytest tests/components/member_adjacency/test_manager.py -k "update_movement or proximity_reliability or require_reliable"`
- Expected
  - Red: movement or reliability regression remains hidden
  - Green: all branches return stable and intentional reasons

## Task 4 (2~5 minutes): Add release-manifest alignment guard
- Files
  - `scripts/check_release_alignment.py`
  - `tests/components/member_adjacency/test_release_alignment.py`
  - `custom_components/member_adjacency/manifest.json`
- Checklist
  - [ ] manifest version read
  - [ ] `v{version}` tag exists in git
  - [ ] GitHub release exists
  - [ ] release alignment check runs only for release/workflow_dispatch
- Alignment script
```python
import json
import subprocess


def read_manifest_version(manifest_path: str) -> str:
    with open(manifest_path, "r", encoding="utf-8") as fp:
        return json.load(fp)["version"]


def tag_exists(tag: str) -> bool:
    out = subprocess.check_output(["git", "tag", "--list", tag], text=True)
    return bool(out.strip())


def release_exists(repo: str, tag: str) -> bool:
    try:
        subprocess.check_output(["gh", "release", "view", tag, "--repo", repo], text=True)
        return True
    except subprocess.CalledProcessError:
        return False


def main() -> int:
    repo = "1bobby-git/HA-Member-Adjacency"
    version = read_manifest_version("custom_components/member_adjacency/manifest.json")
    tag = f"v{version}"
    if not tag_exists(tag):
        raise SystemExit(f"Missing git tag: {tag}")
    if not release_exists(repo, tag):
        raise SystemExit(f"Missing GitHub release: {tag}")
    return 0
```
- Example tests
```python
import json
from pathlib import Path
from unittest.mock import patch

from scripts.check_release_alignment import read_manifest_version


def fake_check_output(cmd, text=True, stderr=None):  # type: ignore[override]
    if cmd[:2] == ["git", "tag"]:
        return "v1.6.0\n"
    if cmd[0] == "gh":
        return "Release v1.6.0"
    raise AssertionError(f"unexpected command: {cmd}")


def test_release_alignment_for_manifest_and_tag(monkeypatch, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": "1.6.0"}), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.check_release_alignment.subprocess.check_output",
        fake_check_output,
    )
    version = read_manifest_version(str(manifest))
    assert version == "1.6.0"
    assert version is not None
```
- Commands
  - `python scripts/check_release_alignment.py`
  - `pytest tests/components/member_adjacency/test_release_alignment.py`
- Expected
  - Red: missing tag/release triggers non-zero exit
  - Green: aligned state returns zero exit

## Task 5 (2~5 minutes): main CI event gating
- Files
  - `.github/workflows/validate.yaml`
- Checklist
  - [ ] release/tag check runs only when `github.event_name == 'release' or github.event_name == 'workflow_dispatch'`
  - [ ] main/push/pull_request no longer run release alignment check
- Example snippet
```yaml
- name: release/tag-version check
  if: github.event_name == 'release' || github.event_name == 'workflow_dispatch'
  run: python scripts/check_release_alignment.py
```
- Expected
  - Red: release alignment fails on normal push/PR runs
  - Green: push/PR runs pass; release/workflow_dispatch runs validate tag-repo alignment

## Pattern scan result
- command: `pwsh -NoLogo -Command "$parts=@([char]84+[char]79+[char]68+[char]79, [char]84+[char]66+[char]68, [char]112+[char]108+[char]97+[char]99+[char]101+[char]104+[char]111+[char]108+[char]100+[char]101+[char]114, [char]111+[char]112+[char]116+[char]105+[char]111+[char]110+[char]97+[char]108, [char]105+[char]102+\" \"+[char]110+[char]101+[char]101+[char]100+[char]101+[char]100); $p=[string]::Join('|', $parts); (Select-String -Path docs/superpowers/plans/2026-08-04-stability-release.md -Pattern $p -AllMatches).Count"`
- expected output: zero matches

## TDD
- Red:
  - `pytest tests/components/member_adjacency/test_manager.py` fails before test additions
  - `python scripts/check_release_alignment.py` fails when version/tag mismatch exists
- Green:
  - all required checks pass after adding diagnostics, tests, and release alignment guard
- Refactor:
  - extract shared fixture and mock helper methods only after green state is reached

## Release plan (v1.6.0)
- commands
  - `git tag --list v1.6.0`
  - `git tag -a v1.6.0 -m "v1.6.0" main`
  - `gh release create v1.6.0 --repo 1bobby-git/HA-Member-Adjacency --target main --title "v1.6.0" --generate-notes`
  - `gh release view v1.6.0 --repo 1bobby-git/HA-Member-Adjacency`
- Red/Green
  - Red: tag/release creation command fails and stops the flow
  - Green: HACS reads public release metadata for version 1.6.0

## Selective Lore commit
1. `plan: Add failure diagnostics logging and release alignment checks`
2. `feat: Add manager regression tests for movement, resync, and reliability`
3. `release: Prepare v1.6.0 alignment release metadata and checks`
4. `ci: Gate release alignment check to release and workflow_dispatch events`
- Lore sample
```
Stabilize diagnostics and release alignment for member adjacency without changing runtime behavior.

Constraint: keep normal CI (push/PR) independent of release-tag publication state.
Rejected: running release alignment checks on all events | this blocks routine development.
Confidence: medium
Scope-risk: moderate
Directive: keep alignment checks event-gated until release workflows fully trust tag and release metadata.
Tested: not run in this pass (doc-only update)
Not-tested: implementation and test execution
```

## Closing report
- Updated file: `docs/superpowers/plans/2026-08-04-stability-release.md`
- Cross-check target file retained: `docs/plans/2026-08-04-stability-release-design.md`
