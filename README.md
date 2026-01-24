# 인접센서 (Member Adjacency Distance)

두 개의 위치(좌표) 엔티티 사이 **거리 / 근접(Proximity)** 을 계산하는 Home Assistant 커스텀 통합입니다.
주로 `mobile_app`의 `*_geocoded_location` 센서를 사용하지만, `device_tracker`, `person`, `zone` 등 **위치(위도/경도)가 포함된 엔티티**도 지원합니다.

> Home Assistant 기본 `proximity` 통합이 "Zone 기준"인 것과 달리, 인접센서는 **엔티티 ↔ 엔티티(좌표 ↔ 좌표)** 관계만 계산합니다.

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
- **근접 업데이트 카운트 (v1.2.0 신규)**
  - `proximity_update_count`: 근접 진입 후 위치 업데이트 횟수
  - `1` = 첫 번째 감지, `2+` = 이후 업데이트
  - 자동화에서 "정확히 1회만 알림" 구현에 활용
- **새로고침 버튼(refresh)**
  버튼을 누르면 가능한 범위에서 "소스 위치 업데이트"를 요청한 뒤, 즉시 재계산합니다.
  - `mobile_app` 기기(가능한 경우): `notify.mobile_app_*`에 `request_location_update` 명령(best-effort)
  - 그 외 엔티티: `homeassistant.update_entity`(best-effort)
  - 이후 즉시 거리/근접/구간 재계산
- **정확도 필터/디바운스**
  - 정확도 속성(`gps_accuracy`/`accuracy`/`horizontal_accuracy`)이 있을 경우 `max_accuracy_m` 기준 필터
  - `debounce_seconds`로 잦은 업데이트 묶음 처리
- **이벤트(Event) 발행**
  - `member_adjacency_enter` : 근접 진입 (1회)
  - `member_adjacency_leave` : 근접 이탈 (1회)
  - `member_adjacency_proximity_update` : 근접 상태에서 위치 업데이트마다 발생 **(v1.2.0 신규)**

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

## Attributes (v1.2.0+)

모든 센서에서 공통으로 제공되는 속성:

| 속성 | 설명 |
|------|------|
| `distance_m` | 거리 (미터, 항상 m 단위) |
| `distance_km` | 거리 (킬로미터) |
| `display_value` | 표시용 값 (자동 m/km 전환) |
| `display_unit` | 표시용 단위 (`m` 또는 `km`) |
| `display_text` | 표시용 텍스트 (예: `1.2 km`) |
| `bucket` | 거리 구간 |
| `proximity` | 근접 여부 (true/false) |
| **`proximity_update_count`** | 근접 진입 후 업데이트 횟수 **(신규)** |
| `proximity_duration_min` | 근접 지속시간 (분) |
| `proximity_duration_human` | 근접 지속시간 (한글) |
| `last_changed` | 근접 상태 변경 시각 |
| `last_entered` | 마지막 근접 진입 시각 |
| `last_left` | 마지막 근접 이탈 시각 |

---

## Events

### `member_adjacency_enter`
근접 진입 시 **1회** 발생

```yaml
event_data:
  entity_a: sensor.a_geocoded_location
  entity_b: sensor.b_geocoded_location
  distance_m: 450
  entry_threshold_m: 500
  exit_threshold_m: 700
  proximity_update_count: 1  # v1.2.0+
```

### `member_adjacency_leave`
근접 이탈 시 **1회** 발생

```yaml
event_data:
  entity_a: sensor.a_geocoded_location
  entity_b: sensor.b_geocoded_location
  distance_m: 720
  entry_threshold_m: 500
  exit_threshold_m: 700
```

### `member_adjacency_proximity_update` (v1.2.0 신규)
근접 상태에서 위치 업데이트마다 발생

```yaml
event_data:
  entity_a: sensor.a_geocoded_location
  entity_b: sensor.b_geocoded_location
  distance_m: 380
  proximity_update_count: 3
  is_first_update: false  # 첫 번째면 true
```

---

## 자동화 예제

### 방법 1: 이벤트 기반 (권장)

`member_adjacency_enter` 이벤트를 사용하면 **근접 진입 시 정확히 1회만** 트리거됩니다.
`input_boolean` 잠금이 필요 없어 가장 간단하고 안정적입니다.

```yaml
alias: "인접센서: 근접 알림 (이벤트 기반)"
description: "근접 진입 시 정확히 1회만 알림"
mode: single
triggers:
  - trigger: event
    event_type: member_adjacency_enter
    event_data:
      entity_a: sensor.member_a_geocoded_location
      entity_b: sensor.member_b_geocoded_location
conditions: []
actions:
  - action: notify.mobile_app_member_a
    data:
      title: "인접 알림"
      message: >
        {% set d = trigger.event.data.distance_m %}
        {% if d >= 1000 %}
          B와의 거리: {{ (d / 1000) | round(1) }}km
        {% else %}
          B와의 거리: {{ d | int }}m
        {% endif %}
      data:
        push:
          category: map
        action_data:
          latitude: "{{ state_attr('person.member_b','latitude') }}"
          longitude: "{{ state_attr('person.member_b','longitude') }}"
```

### 방법 2: 상태 기반 + proximity_update_count

기존 버킷/상태 기반 트리거를 유지하면서 `proximity_update_count == 1` 조건으로 첫 감지만 처리:

```yaml
alias: "인접센서: 근접 알림 (상태 기반)"
description: "proximity_update_count를 이용한 1회 알림"
mode: single
triggers:
  - trigger: state
    entity_id: binary_sensor.member_adjacency_<PAIR>_proximity
    to: "on"
conditions:
  - condition: template
    value_template: >
      {{ state_attr('binary_sensor.member_adjacency_<PAIR>_proximity',
         'proximity_update_count') == 1 }}
actions:
  - action: notify.mobile_app_member_a
    data:
      title: "인접 알림"
      message: >
        {% set d = states('sensor.member_adjacency_<PAIR>') | float(0) %}
        {% set txt = state_attr('sensor.member_adjacency_<PAIR>', 'display_text') %}
        B와의 거리: {{ txt }}
```

### 방법 3: 기존 방식 (input_boolean 잠금)

예제 파일: [`examples/template.yaml`](examples/template.yaml)

> **참고**: v1.2.0부터는 방법 1 또는 2를 권장합니다. 이벤트/속성 기반이 더 정확하고 `input_boolean` helper가 필요 없습니다.

---

## 거리 표시 형식

알림 메시지에서 거리를 표시할 때 자동 단위 변환:

```yaml
# 방법 1: 직접 계산
message: >
  {% set d = states('sensor.member_adjacency_<PAIR>') | float(0) %}
  {% if d >= 1000 %}
    거리: {{ (d / 1000) | round(1) }}km
  {% else %}
    거리: {{ d | int }}m
  {% endif %}

# 방법 2: display_text 속성 사용 (더 간단)
message: >
  거리: {{ state_attr('sensor.member_adjacency_<PAIR>', 'display_text') }}
```

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

## Version History

### v1.2.0 (2025-01-24)
**주요 기능 추가: 근접 업데이트 카운트**

- **`proximity_update_count` 속성 추가**
  - 근접 진입 후 위치 업데이트 횟수 추적
  - `1` = 첫 번째 감지 (알림 발송에 활용)
  - `2+` = 이후 업데이트 (중복 알림 방지)
  - 근접 이탈 시 `0`으로 초기화

- **`member_adjacency_proximity_update` 이벤트 추가**
  - 근접 상태에서 위치 업데이트마다 발생
  - `is_first_update`: 첫 번째 업데이트 여부
  - `proximity_update_count`: 현재 업데이트 횟수

- **`member_adjacency_enter` 이벤트 개선**
  - `proximity_update_count: 1` 데이터 추가

- **자동화 개선**
  - 이벤트 기반 방식으로 `input_boolean` 잠금 없이 정확히 1회만 알림 가능
  - 중복 알림 문제 근본적 해결

### v1.1.8 (2025-01-19)
- Release 안정화

### v1.1.7 (2025-01-18)
- 통계 수정: 거리를 항상 미터로 저장, m/km 자동 전환은 속성으로 제공
- `display_value`, `display_unit`, `display_text` 속성 추가

### v1.1.6 (2025-01-15)
- 새로고침 버튼이 소스 위치 업데이트 요청
- 엔티티 선택기 유형별 그룹화 및 정렬
- 근접 지속시간 한글 형식
- 거리 소수점 1자리

### v1.1.5 (2025-01-12)
- 기기 이름 표시 개선
- 좌표 없는 엔티티 숨김

### v1.1.4 (2025-01-10)
- 문서 업데이트
- brands 아이콘 준비

### v1.1.2 (2025-01-08)
- 기기 + 새로고침 버튼
- 엔티티별 아이콘
- bearing 제거

### v1.1.1 (2025-01-05)
- coordinator debouncer 오류 수정
- A-B pair 모델로 복귀

### v1.1.0 (2025-01-01)
- 멀티 타겟 근접
- 바이너리 센서 + 이벤트
- 히스테리시스 + 디바운스
- 버킷 + bearing

### v1.0.0 (2024-12-15)
- 최초 릴리즈

---

## License

MIT License
