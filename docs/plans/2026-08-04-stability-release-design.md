# HA-Member-Adjacency 안정성 + 릴리스 정합성 설계 계획
상태: Draft  
작성일: 2026-08-04  
범위: docs-only 실행 지침 + 구현 계획 (코드 변경/커밋/푸시는 제외, 문서 산출물만 작성)

## 목적
- `manager.py` 핵심 경로의 회귀 위험을 낮추고, `async_request_source_update` 실패의 진단 가능성을 높이며, `1.6.0` 버전의 배포 정합성을 확보한다.
- HA/HACS 릴리스 파이프라인에서 manifest/tag/release 정합 불일치를 해소해 사용자 업데이트 노출을 보장한다.

## 승인된 개선안(고정)
1. `async_request_source_update`에서 서비스 실패를 비파괴적으로 로깅하여 진단성 향상  
2. `AdjacencyManager` 핵심 경로 회귀 테스트 도입 (리팩토링/기능 변경 방지)  
3. `manifest.json` 버전/`git tag`/GitHub Release 정합성 점검 및 `v1.6.0` 공개 릴리스 준비  

## 요구사항 제약
- 소유 범위: 오직 아래 두 파일만 작성/수정
  - `docs/plans/2026-08-04-stability-release-design.md`
  - `docs/superpowers/plans/2026-08-04-stability-release.md`
- 코드/테스트 구현, 커밋, 푸시 실행하지 않음
- 타인 변경물 되돌리기 금지
- 한국어 사용자 설명 우선, 기술 항목은 파일/심볼/명령어 기준으로 구체화

## 작업 체크리스트
- [ ] 1단계: 진단 및 버전 정합성 베이스라인 기록
  - [ ] `custom_components/member_adjacency/manifest.json` 값 검토
  - [ ] `git describe --tags --abbrev=0` 실행 기록
  - [ ] `git tag` 및 `gh release list --repo 1bobby-git/HA-Member-Adjacency --limit 20` 결과 비교
  - [ ] `custom_components/member_adjacency/manager.py` 실패 진단 포인트와 의존 호출 목록 매핑
- [ ] 2단계: `async_request_source_update` 진단 계획 확정
  - [ ] 실패 포인트별 코드 경로 식별:
    - `manager.py: async_request_source_update`
    - `manager.py: _mobile_app_identifier_from_entity`
    - `hass.services.has_service("notify", service)`
    - `hass.services.async_call("notify", service, ...)`
    - `hass.services.async_call("homeassistant", "update_entity", ...)`
  - [ ] 비파괴 로그 규격 확정 (`debug` 레벨 + 에러 코드 + entity_id + service + exception 타입)
- [ ] 3단계: manager 핵심 경로 회귀 테스트 계획 확정
  - [ ] 대상 경로/심볼:
    - `AdjacencyManager._check_proximity_reliability`
    - `AdjacencyManager._update_movement`
    - `AdjacencyManager.async_refresh`
    - `AdjacencyManager.async_migrate_entry`는 별도 마이그레이션 규칙 연계 테스트로 보강
  - [ ] 테스트 시나리오 정의:
    - 이동 속도 초과 필터 경로(`speed_filtered_a`, `speed_filtered_b`)에서 `data_valid=False` 유지
    - 대기시간/재동기화 경로(`resync_*`)에서 거리 업데이트 보류 및 이벤트 비발생
    - 정확도 필터(`max_accuracy_m`) 위반 시 `missing_coords`와 구분되는 오류 경로
    - 신뢰도 조건 미달(`require_reliable_proximity=True`) 시 enter 이벤트 차단 + `member_adjacency_enter_unreliable`만 발생
    - `entry_threshold_m`, `exit_threshold_m` 경계값 전환 시 지연/디바운스 동작 유지
- [ ] 4단계: 릴리스 패키징/버전 정합 계획 확정
  - [ ] `manifest.json`에서 현재 버전 확인: `version: 1.6.0`
  - [ ] `hacs.json` 확인:
    - `homeassistant: 2024.12.0`
    - `zip_release: false`
  - [ ] `git tag` 미스매치 시 태그 생성 절차 문서화
  - [ ] GitHub release 메모 포맷 고정 (`v1.6.0` 제목/본문/체인지로그 포함)

## 실제 코드(구현 시 반영할 변경점)
> 본 문서는 코드 작성 지시서이며, 실제 수정은 본 범위 외 문맥에서 수행한다.

### A. `manager.py` 진단 로깅 계획
- 대상 심볼: `AdjacencyManager.async_request_source_update`
- 구현 포인트:
  - 서비스 호출 실패 시 `except Exception`에서 `self.mgr.data.last_error`에 문자열 저장하지 않고
    `hass` 로거를 통해 비파괴 로그만 남김
  - 실패 케이스 메시지 예시:
    - `"member_adjacency: notify_service_call_failed"` (`service` 이름, `entity_id`)
    - `"member_adjacency: homeassistant_update_entity_failed"` (`entity_id`, `exception`)
  - 상태값은 기존 동작 유지(강제 예외 전파 없이 현재 `Press`/`refresh` 동작 지속)

### B. manager 핵심 경로 회귀 테스트 추가 계획
- 신규 테스트 파일(생성 시):
  - `tests/components/member_adjacency/test_manager.py`
  - `tests/components/member_adjacency/test_config_flow.py` (옵션/입력 유효성 보완)
- 핵심 검증 코드 대상:
  - `AdjacencyManager.async_refresh()`
  - `AdjacencyManager._update_movement()`
  - `AdjacencyManager._check_proximity_reliability()`
- 어서션 키:
  - `data_valid`, `last_error`, `data.proximity`, `data.proximity_reliable`, 이벤트 발행 횟수
- 테스트 의도 라벨:
  - `RED`: 새 규칙 반영 전 실패하는 테스트명과 기대 실패 시나리오 명시
  - `GREEN`: 구현 반영 후 각 시나리오가 통과

### C. 릴리스/태그 정합성 문서 점검 항목
- `custom_components/member_adjacency/manifest.json`
- `git tag --list "v*"` 결과
- `gh release list --repo 1bobby-git/HA-Member-Adjacency`
- `gh release view v1.6.0 --repo 1bobby-git/HA-Member-Adjacency`

## 명령 체크리스트 (예상 출력 포함)
1. `git tag --list`
   - 기대 결과: 현재 최신 태그가 `v1.5.2` 또는 그 미만이면 `v1.6.0` 미싱 확인
2. `python - <<'PY' ...` 또는 `Get-Content custom_components/member_adjacency/manifest.json`
   - 기대 결과: manifest `version`이 `1.6.0` 확인
3. `gh release list --repo 1bobby-git/HA-Member-Adjacency --limit 20`
   - 기대 결과: 릴리스 목록에 `v1.6.0` 부재
4. `git diff --name-only v1.5.2..main`
   - 기대 결과: 최근 변경 요약이 `feat: HA 2024.12+ OptionsFlow 및 메타데이터 정리` 단일 커밋으로 수렴

## TDD Red-Green 계획
- Red: 테스트 명세를 먼저 정리해 실패 상태를 고정
  - 실패 조건 1: `resync` 구간에서도 잘못된 근접 이벤트가 발생
  - 실패 조건 2: 이동 속도 과다 시 거리 갱신이 계속됨
  - 실패 조건 3: `require_reliable_proximity=True`인데도 enter 이벤트가 항상 발생
- Green: 해당 테스트 통과를 목표로 구현 반영
- Refactor: 테스트-코드 동기화 후 경량 리팩토링 후 재실행

## Selective commit 전략 (참조용)
- 변경 분할 원칙 (코드 구현 단계에서만 적용, 현재 문서 범위에서는 계획으로만 남김)
  - Commit 1: `manager.py` 진단 로그만 수정
  - Commit 2: 테스트 추가/보강
  - Commit 3: 릴리스 메타/문서 정합성 조정
  - Commit 4: 태그+릴리스 업로드
- 각 커밋은 단일 목적 유지(리스크 최소화, rollback 가능성 확보)

## Lore 메시지 템플릿 (구현 완료시 사용)
```
Stabilize member adjacency diagnostics and ensure HA/HACS version-release consistency by adding non-destructive refresh failure visibility and release-grounded validation gates.

Constraint: Preserve current runtime behavior while making failure states observable and improving confidence for proximity logic changes.
Rejected: Swallowing failures without observability | causes untraceable stale-refresh incidents
Confidence: medium
Scope-risk: moderate
Directive: Re-run release-validation and HACS visibility checks after v1.6.0 tag/release before wider rollout.
Tested: [추후 채우기]
Not-tested: [구현 전 계획 상태]
```

## 완료 기준 및 HACS/릴리스 검증
- [ ] `v1.6.0` 태그 생성 및 GitHub release 생성 완료
- [ ] 릴리스 본문에 변경 로그와 확인용 체크리스트 포함
- [ ] HACS에 `v1.6.0`가 표시됨(브라우저/테스트 환경 기준)
- [ ] `data_valid`/`last_error`/`proximity` 회귀 시나리오 테스트 항목이 문서화된 대로 모두 통과
- [ ] `async_request_source_update` 장애 시점 로그가 남아 원인 추적 가능

## 다음 단계 (구현 전 승인 후 실행)
- 구현자는 본 문서 항목을 그대로 가져가 `code+tests` 브랜치 또는 작업 브랜치에서 실행하고, 구현 완료 시 각 체크박스 및 기대 결과를 증빙 로그로 채운다.
