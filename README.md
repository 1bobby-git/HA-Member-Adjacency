# 인접센서 (Member Adjacency Distance)

두 개의 위치(좌표) 엔티티 사이 **거리 / 근접(Proximity)** 을 계산하는 Home Assistant 커스텀 통합입니다.  
주로 `mobile_app` 통합에서 제공되는 `*_geocoded_location` 센서(속성 `Location=[lat, lon]`)를 대상으로 사용합니다.

> Home Assistant 기본 `proximity` 통합이 “Zone 기준”인 것과 달리, 인접센서는 **엔티티 ↔ 엔티티(좌표 ↔ 좌표)** 간의 관계만 계산합니다.  
> (Zone 엔티티는 지원하지 않습니다.)

---

## Features

- **거리 센서(distance)**  
  - 두 엔티티 간 거리를 계산합니다.
  - 기본 동작: 1000m 미만은 **m**, 1000m 이상은 **km**로 자동 전환
  - 옵션 `force_meters`를 켜면 항상 **m**로 고정
- **근접 바이너리 센서(proximity)**  
  - 임계값 이내 접근 여부를 `on/off`로 제공합니다.
  - 히스테리시스 적용(깜빡임 완화):
    - `entry_threshold_m` 이하로 들어오면 **on**
    - `exit_threshold_m` 이상으로 벗어나면 **off**
- **구간 센서(bucket)**  
  - 거리 구간을 텍스트로 제공합니다: `very_near / near / mid / far / very_far`
- **근접 지속 시간 센서(proximity duration)**  
  - 근접이 `on` 상태로 유지된 시간을 분(min) 단위로 제공합니다. (소수점 1자리)
- **새로고침 버튼(refresh)**  
  - 버튼을 누르면:
    1) 가능하면 `homeassistant.update_entity`로 A/B 엔티티 업데이트를 요청하고
    2) 즉시 현재 좌표를 다시 읽어 거리/근접을 재계산합니다.
- **안정성(좌표 누락/정확도 문제)**
  - 좌표를 일시적으로 읽지 못하면(누락/정확도 필터) **마지막 정상 계산값을 유지**합니다.
  - 속성으로 `data_valid`, `last_valid_updated`, `last_error`를 제공합니다.
- **정확도 필터/디바운스**
  - `gps_accuracy` / `accuracy` / `horizontal_accuracy` 속성이 있으면 `max_accuracy_m` 기준으로 필터링
  - `debounce_seconds`로 잦은 업데이트 묶음 처리
- **이벤트(Event) 발행**
  - `member_adjacency_enter` : 근접으로 바뀌는 순간
  - `member_adjacency_leave` : 비근접으로 바뀌는 순간

---

## Install (HACS)

아래 버튼을 누르면 Home Assistant에서 HACS 커스텀 레포 추가 화면으로 이동합니다.

[![Open your Home Assistant instance and show the HACS repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=1bobby-git&repository=HA-Member-Adjacency&category=integration)

1. HACS → Integrations → 우측 상단 ⋮ → Custom repositories  
2. Repository: `https://github.com/1bobby-git/HA-Member-Adjacency`  
3. Category: Integration  
4. 설치 후 Home Assistant 재시작

---

## Setup

통합 추가 화면으로 바로 이동하는 버튼입니다.

[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=member_adjacency)

1. 설정 → 기기 및 서비스 → 통합 추가 → **인접센서**
2. Entity A / Entity B 선택  
   - 추천: `sensor.*_geocoded_location` (mobile_app)
   - 추가 지원: `person.*`, `device_tracker.*`, `sensor.*` (단, 위도/경도 속성이 존재해야 함)
3. 임계값/옵션 입력 후 완료

---

## Supported coordinate formats

아래 중 하나면 동작합니다.

- `attributes.Location == [lat, lon]` (권장; mobile_app geocoded sensor)
- `attributes.latitude` 와 `attributes.longitude`
- state 가 `"lat,lon"` 문자열

---

## Options

- `entry_threshold_m` : 진입 임계값 (이 값 이하이면 proximity=on)
- `exit_threshold_m` : 이탈 임계값 (이 값 이상이면 proximity=off)  
  - `exit_threshold_m >= entry_threshold_m` 이어야 함
- `debounce_seconds` : 디바운스 (초)
- `max_accuracy_m` : 최대 허용 정확도 (m, 0=무시)
- `force_meters` : 단위를 항상 m로 고정

---

## Entities created (per A-B pair)

A-B 한 쌍을 추가하면, 해당 쌍은 **하나의 기기(Device)** 로 묶여 생성되며 아래 엔티티들이 포함됩니다.

- `sensor.member_adjacency_<pair>` : 거리 (m/km 자동 전환 또는 m 고정, 소수점 1자리)
- `sensor.member_adjacency_<pair>_bucket` : 거리 구간
- `sensor.member_adjacency_<pair>_proximity_duration` : 근접 지속 시간(분, 소수점 1자리)
- `binary_sensor.member_adjacency_<pair>_proximity` : 근접 여부(on/off)
- `button.member_adjacency_<pair>_refresh` : 새로고침(업데이트 요청 + 즉시 재계산)

> 다른 쌍(A-C 등)이 필요하면 통합을 **다시 추가**하여 여러 엔트리를 만들 수 있습니다.

---

## Proximity (근접) 활용

근접 바이너리 센서는 자동화에서 가장 자주 사용됩니다.

- 조건 예: `binary_sensor.member_adjacency_..._proximity == on`
- 활용 예: 가족이 일정 거리 이내로 접근하면 알림/조명/문열림 등

히스테리시스(진입/이탈 임계값 분리)로 경계 근처에서 상태가 반복적으로 바뀌는 현상을 줄입니다.

---

## Events

근접 상태가 변할 때 이벤트가 발생합니다.

- `member_adjacency_enter`
- `member_adjacency_leave`

Payload 예:
- `entity_a`, `entity_b`
- `distance_m`
- `entry_threshold_m`, `exit_threshold_m`

---

## Debug (Logs)

`configuration.yaml`:

    logger:
      default: info
      logs:
        custom_components.member_adjacency: debug
