# 인접센서 (Member Adjacency Distance)

두 개의 위치(좌표) 엔티티 사이 **거리 / 근접(Proximity)** 을 계산하는 Home Assistant 커스텀 통합입니다.  
주로 `mobile_app`의 `*_geocoded_location` 센서를 사용하지만, `device_tracker`, `person`, `zone` 등 **위치(위도/경도)가 포함된 엔티티**도 지원합니다.

> Home Assistant 기본 `proximity` 통합이 “Zone 기준”인 것과 달리, 인접센서는 **엔티티 ↔ 엔티티(좌표 ↔ 좌표)** 관계만 계산합니다.

---

## Features

- **거리 센서(distance)**  
  - 두 엔티티 간 거리를 계산합니다.
  - 기본 동작: 1000m 미만은 **m**, 1000m 이상은 **km**로 자동 전환
  - 표시 정밀도: **소수점 1자리**
  - 옵션 `force_meters`를 켜면 항상 **m**로 고정
- **근접 바이너리 센서(proximity)**  
  - 임계값 이내 접근 여부를 `on/off`로 제공합니다.
  - 히스테리시스:
    - `entry_threshold_m` 이하로 들어오면 **on**
    - `exit_threshold_m` 이상으로 벗어나면 **off**
- **구간 센서(bucket)**  
  - 거리 구간: `very_near / near / mid / far / very_far`
- **근접 지속시간 센서(proximity duration)**  
  - `5분`, `1시간 20분`처럼 사람이 읽기 쉬운 형태로 표시합니다.
  - 숫자(분)는 `attributes.proximity_duration_min`로도 제공됩니다.
- **새로고침 버튼(refresh)**  
  버튼을 누르면 가능한 범위에서 “소스 위치 업데이트”를 요청한 뒤, 즉시 재계산합니다.
  - `mobile_app` 기기(가능한 경우): `notify.mobile_app_*`에 `request_location_update` 명령(best-effort)
  - 그 외 엔티티: `homeassistant.update_entity`(best-effort)
  - 이후 즉시 거리/근접/구간 재계산
- **정확도 필터/디바운스**
  - 정확도 속성(`gps_accuracy`/`accuracy`/`horizontal_accuracy`)이 있을 경우 `max_accuracy_m` 기준 필터
  - `debounce_seconds`로 잦은 업데이트 묶음 처리
- **이벤트(Event) 발행**
  - `member_adjacency_enter` : 근접 진입
  - `member_adjacency_leave` : 근접 이탈

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

- `entry_threshold_m` : 진입 임계값 (이 값 이하이면 proximity=on)
- `exit_threshold_m` : 이탈 임계값 (이 값 이상이면 proximity=off)  
  - `exit_threshold_m >= entry_threshold_m` 이어야 함
- `debounce_seconds` : 디바운스 (초)
- `max_accuracy_m` : 최대 허용 정확도 (m, 0=무시)
- `force_meters` : 단위를 항상 m로 고정

---

## Entities created (per A-B pair)

A-B 한 쌍을 추가하면, 해당 쌍은 **하나의 기기(Device)** 로 묶여 생성되며 아래 엔티티들이 포함됩니다.

- `sensor.member_adjacency_<pair>` : 거리 (m/km 자동 전환, 소수점 1자리)
- `binary_sensor.member_adjacency_<pair>_proximity` : 근접 여부(on/off)
- `sensor.member_adjacency_<pair>_bucket` : 거리 구간
- `sensor.member_adjacency_<pair>_proximity_duration` : 근접 지속시간(예: `1시간 20분`)
- `button.member_adjacency_<pair>_refresh` : 새로고침(업데이트 요청 + 즉시 재계산)

> 다른 쌍(A-C 등)이 필요하면 통합을 **다시 추가**하여 여러 엔트리를 만들 수 있습니다.

---

## Events

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
