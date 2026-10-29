<!-- project-branding:start -->
<p align="center">
  <img src="https://raw.githubusercontent.com/1bobby-git/HA-Member-Adjacency/v1.6.3/custom_components/member_adjacency/brand/logo@2x.png" alt="인접센서 로고" width="520">
</p>
<p align="center">
  <a href="https://github.com/1bobby-git/HA-Member-Adjacency/stargazers"><img src="https://img.shields.io/github/stars/1bobby-git/HA-Member-Adjacency?style=flat-square&logo=github&label=Stars" alt="GitHub Stars"></a>
  <a href="https://github.com/1bobby-git/HA-Member-Adjacency/releases"><img src="https://img.shields.io/github/v/release/1bobby-git/HA-Member-Adjacency?style=flat-square&label=Release" alt="Latest Release"></a>
  <a href="https://github.com/1bobby-git/HA-Member-Adjacency/blob/main/custom_components/member_adjacency/manifest.json"><img src="https://img.shields.io/badge/Architecture-independent-0ea5e9?style=flat-square" alt="Architecture independent"></a>
  <a href="https://github.com/1bobby-git/HA-Member-Adjacency/blob/main/LICENSE"><img src="https://img.shields.io/github/license/1bobby-git/HA-Member-Adjacency?style=flat-square&label=License" alt="License"></a>
  <a href="https://github.com/1bobby-git/HA-Member-Adjacency/commits/main"><img src="https://img.shields.io/github/last-commit/1bobby-git/HA-Member-Adjacency?style=flat-square&label=Updated" alt="Last Commit"></a>
</p>
<!-- project-branding:end -->

# 인접센서 (Member Adjacency Distance)


> **Compatibility**: Home Assistant **2024.12+** 권장 (OptionsFlow / DeviceInfo / Coordinator API 정리 반영).
두 개의 위치(좌표) 엔티티 사이 **거리 / 근접(Proximity)** 을 계산하는 Home Assistant 커스텀 통합입니다.
주로 `mobile_app`의 `*_geocoded_location` 센서를 사용하지만, `device_tracker`, `person`, `zone` 등 **위치(위도/경도)가 포함된 엔티티**도 지원합니다.

> Home Assistant 기본 `proximity` 통합이 "Zone 기준"인 것과 달리, 인접센서는 **엔티티 ↔ 엔티티(좌표 ↔ 좌표)** 관계만 계산합니다.

---

## Features

- **거리 센서(distance)**
  - 두 엔티티 간 거리를 계산합니다.
  - 상태값은 항상 **m** 단위입니다.
  - `display_value`·`display_unit`·`display_text` 속성은 1000m 미만은 **m**, 1000m 이상은 **km**로 바꿔 보여 줍니다.
  - 표시 정밀도: **소수점 1자리**
  - 옵션 `force_meters`를 켜면 표시 속성도 항상 **m**로 고정
- **근접 바이너리 센서(proximity)**
  - 임계값 이내 접근 여부를 `on/off`로 제공합니다.
  - 히스테리시스:
    - `entry_threshold_m` 이하로 들어오면 **on**
    - `exit_threshold_m` 이상으로 벗어나면 **off**
  - GPS 신뢰도 조건(고급 설정)은 **on이 될 때만** 적용합니다. on이 된 뒤에는 거리만으로 off가 됩니다.
  - Home Assistant 재시작이나 옵션 저장 뒤에도 이전 근접 상태를 이어 갑니다(이 바이너리 센서를 비활성화하면 상태를 저장하지 않으므로 이어 가지 않습니다).
- **구간 센서(bucket)**
  - 거리 구간: `very_near / near / mid / far / very_far`
- **근접 지속시간 센서(proximity duration)**
  - `5분`, `1시간 20분`처럼 사람이 읽기 쉬운 형태로 표시합니다.
  - 근접 중에는 1분마다 갱신됩니다.
  - 숫자(분)는 `attributes.proximity_duration_min`로도 제공됩니다.
- **근접 업데이트 카운트(proximity_update_count)**
  - 근접 진입 후 위치 업데이트 횟수를 추적합니다.
  - `1` = 첫 번째 감지, `2+` = 이후 업데이트, `0` = 근접 이탈
  - 자동화에서 **"정확히 1회만 알림"** 구현 시 `input_boolean` 잠금 없이 사용 가능
- **새로고침 버튼(refresh)**
  - 버튼을 누르면 휴대폰(`mobile_app`)에 위치 갱신 요청(`request_location_update`)을 보내고 `homeassistant.update_entity`를 호출한 뒤, 즉시 재계산합니다.
  - 재계산 자체는 위치 갱신으로 세지 않습니다(신뢰도 조건의 갱신 횟수, `proximity_update_count`, `proximity_update` 이벤트 모두). 휴대폰이 보낸 새 위치는 일반 위치 갱신과 같이 처리합니다. 오래 조용하던 휴대폰의 첫 위치는 재동기화 보류를 거칩니다.
- **정확도 필터/디바운스**
  - 정확도 속성이 있을 경우 `max_accuracy_m` 기준 필터
  - `debounce_seconds`로 잦은 업데이트 묶음 처리
- **이벤트(Event) 발행**
  - `member_adjacency_enter` : 근접 진입 (1회)
  - `member_adjacency_enter_unreliable` : 거리는 가깝지만 GPS 신뢰도 조건을 채우지 못함 (1회)
  - `member_adjacency_leave` : 근접 이탈 (1회)
  - `member_adjacency_proximity_update` : 근접 상태에서 위치 업데이트마다 발생

---

## Install (HACS)

[![Open your Home Assistant instance and show the HACS repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=1bobby-git&repository=HA-Member-Adjacency&category=integration)

1. HACS → Integrations → 우측 상단 ⋮ → Custom repositories
2. Repository: `https://github.com/1bobby-git/HA-Member-Adjacency`
3. Category: Integration
4. 설치 후 Home Assistant 재시작

---

## Setup

[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=member_adjacency)

1. 설정 → 기기 및 서비스 → 통합 추가 → **인접센서**
2. Entity A / Entity B 선택
   - 유형별로 정리되어 표시됩니다(Geocoded / Device Tracker / Person / Zone / Sensor)
   - 각 유형 내에서는 **가나다(라벨 기준) 정렬**
   - 좌표가 없는 엔티티는 목록에 표시되지 않습니다.
3. 임계값/옵션 입력 후 완료

---

## Supported coordinate formats

아래 중 하나면 동작합니다.

- `attributes.Location == [lat, lon]` (권장; mobile_app geocoded sensor)
- `attributes.latitude` 와 `attributes.longitude`
- state 가 `"lat,lon"` 문자열

---

## Options

| 옵션 | 설명 |
|------|------|
| `entry_threshold_m` | 진입 임계값 (이 값 이하이면 proximity=on) |
| `exit_threshold_m` | 이탈 임계값 (이 값 이상이면 proximity=off) |
| `debounce_seconds` | 디바운스 (초) |
| `max_accuracy_m` | 최대 허용 정확도 (m, 0=무시) |
| `force_meters` | 표시 단위를 항상 m로 고정 |

> `exit_threshold_m >= entry_threshold_m` 이어야 합니다.

고급 설정(GPS 신뢰도·재동기화):

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `resync_silence_s` | 600 | 이 시간(초) 동안 갱신이 없다가 들어온 위치를 재동기화로 보고 보류 |
| `resync_hold_s` | 60 | 재동기화 보류 시간(초). 보류 중에는 어느 쪽 갱신이나 새로고침이 와도 이전 상태를 유지하고, 끝나면 다시 계산 |
| `max_speed_kmh` | 150 | 이 속도를 넘는 위치 이동은 비정상으로 보고 거부. 다음 정상 위치까지 근접 센서는 `unavailable` (0=끄기, 접근 속도 검사도 꺼짐) |
| `min_updates_for_proximity` | 3 | 근접 진입을 신뢰하려면 양쪽이 `update_window_s` 안에 갱신돼야 하는 횟수 |
| `update_window_s` | 300 | 갱신 횟수를 세는 시간 범위(초) |
| `require_reliable_proximity` | 켜짐 | 켜면 신뢰도 조건을 채워야 근접 on과 `enter` 이벤트가 발생하고, 못 채우면 `enter_unreliable` 이벤트만 발생 |

> `zone.*` 엔티티는 위치가 고정이므로 갱신 횟수 조건과 재동기화 보류를 적용하지 않습니다.

---

## Entities created (per A-B pair)

A-B 한 쌍을 추가하면, 해당 쌍은 **하나의 기기(Device)** 로 묶여 생성되며 아래 엔티티들이 포함됩니다.

| 엔티티 | 설명 |
|--------|------|
| `sensor.member_adjacency_<pair>` | 거리 (m/km 자동 전환) |
| `binary_sensor.member_adjacency_<pair>_proximity` | 근접 여부 (on/off) |
| `sensor.member_adjacency_<pair>_bucket` | 거리 구간 |
| `sensor.member_adjacency_<pair>_proximity_duration` | 근접 지속시간 |
| `button.member_adjacency_<pair>_refresh` | 새로고침 버튼 |

> 다른 쌍(A-C 등)이 필요하면 통합을 **다시 추가**하여 여러 엔트리를 만들 수 있습니다.

---

## Events

| 이벤트 | 발생 시점 | 포함 데이터 |
|--------|----------|-------------|
| `member_adjacency_enter` | 근접 진입 (1회) | entity_a, entity_b, distance_m, proximity_update_count |
| `member_adjacency_enter_unreliable` | 거리는 진입 임계값 안이지만 신뢰도 조건 미충족 (1회) | entity_a, entity_b, distance_m, proximity_reliable, unreliable_reason |
| `member_adjacency_leave` | 근접 이탈 (1회) | entity_a, entity_b, distance_m |
| `member_adjacency_proximity_update` | 근접 중 위치 업데이트마다 (`require_reliable_proximity`가 켜져 있으면 신뢰할 수 있는 업데이트만) | entity_a, entity_b, distance_m, proximity_update_count, is_first_update |

---

## 자동화 예제

`member_adjacency_enter` 이벤트를 트리거로 사용하면 근접 진입 시 **정확히 1회만** 알림을 보낼 수 있습니다.
기존처럼 `input_boolean` 잠금이 필요 없어 자동화가 간단해집니다.

예제 파일: [`examples/template.yaml`](examples/template.yaml)

---

## Debug (Logs)

`configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.member_adjacency: debug
```

---

## License

MIT License

## 통합 업데이트 1.6.5

- 최근 위치 이력 집계의 전체 순회를 이진 탐색으로 교체
- 만료 항목이 없으면 이력 리스트를 매번 재생성하지 않음; 시각 역행 시에도 정렬 유지
- 디바운스·이벤트 횟수·신뢰도 임계값·거리 계산·근접 자동화·통합 목록 노출은 변경하지 않음

변경 내용, 검증 범위 및 롤백 방법: [최적화 문서](docs/OPTIMIZATION_2026-09-06.md). 펌웨어·브리지 앱은 변경하지 않으며, 운영 HA 설치·실기기 검증은 별도입니다.

## 통합 업데이트 1.6.6

- GPS 좌표의 NaN·무한대·위도/경도 범위 초과 값을 거리 계산 전에 제외합니다.
- Location 속성, latitude/longitude 속성, 문자열 좌표에 같은 검증을 적용합니다.

실제 Home Assistant 설치 및 기기 검증은 별도입니다.

## 통합 업데이트 1.6.7

- 설정 항목 언로드·리로드 시 예약된 새로고침 작업을 취소해, 해제된 매니저에서 이벤트가 뒤늦게 발생하거나 작업이 누수되지 않도록 했습니다.
- 두 대상이 멈춰 있어 수렴 속도가 정확히 `0.0 km/h`일 때 `member_adjacency_enter` 이벤트가 값을 `null` 대신 `0.0`으로 전달하도록 수정했습니다.
- 엔티티 ID·unique ID·설정 항목 키·서비스·이벤트 이름은 변경하지 않았습니다.

실제 Home Assistant 설치 및 기기 검증은 별도입니다.

## 통합 업데이트 1.6.8

- 근접이 켜진 뒤에는 이탈 임계값을 넘을 때만 꺼집니다. 함께 있는 동안 한쪽 위치 갱신이 뜸해져 `leave`와 `enter`가 반복되던 문제를 고쳤습니다. 근접 중 신뢰할 수 없는 갱신은 `proximity_update`로 보내지 않습니다.
- `zone` 엔티티를 기준으로 한 쌍도 근접이 켜집니다.
- 오래 조용하던 위치가 들어와 재동기화로 보류될 때 근접 센서가 `unavailable`이 되지 않고 이전 상태를 유지합니다. 보류 중에는 반대쪽 갱신이나 새로고침 버튼도 근접 상태를 바꾸지 않고, 보류가 끝나면 다시 계산합니다.
- 재시작·옵션 저장 뒤에도 근접 상태·진입 시각·업데이트 횟수를 이어 가므로 `enter`가 다시 발생하지 않습니다. 저장은 1.6.8부터 시작하므로, 업데이트 직후 첫 시작은 예전처럼 처음부터 계산합니다. 근접 바이너리 센서를 비활성화하면 저장하지 않습니다.
- 새로고침 버튼이 휴대폰에 위치 갱신 요청을 실제로 보냅니다(`notify.mobile_app_<기기 이름>`, `person`은 현재 위치를 제공하는 기기 추적기).
- 근접 지속시간 센서가 근접 중 1분마다 갱신됩니다. 매분 바뀌는 두 속성(`proximity_duration_min`, `proximity_duration_human`)은 이 센서에서 기록(recorder)하지 않습니다.
- 시작·새로고침 버튼·보류 종료의 재계산은 위치 갱신으로 세지 않습니다. 버튼을 여러 번 눌러 신뢰도 조건을 채울 수 없고, 근접 중 버튼을 눌러도 `proximity_update` 이벤트와 `proximity_update_count`가 늘지 않습니다(1.6.7에서는 늘었음).
- `max_speed_kmh = 0`이면 접근 속도 검사도 끕니다. 거리 계산이 수렴하지 않으면 그 위치를 무효로 처리합니다. 플랫폼 설정이 실패하면 매니저를 정리한 뒤 오류를 그대로 알립니다. 설정 화면도 NaN·범위 밖 좌표를 거부합니다.
- 엔티티 ID·unique ID·설정 키·기본값·이벤트 이름과 payload 키·거리 계산은 변경하지 않았습니다.

실제 Home Assistant 설치 및 기기 검증은 별도입니다.
