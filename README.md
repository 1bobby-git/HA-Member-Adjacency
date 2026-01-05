# 인접센서 (Member Adjacency Distance)

두 개의 위치(좌표) 엔티티 사이 **거리 / 근접(Proximity)** 을 계산하는 Home Assistant 커스텀 통합입니다.  
주로 `mobile_app` 통합에서 제공되는 `*_geocoded_location` 센서(속성 `Location=[lat, lon]`)를 대상으로 사용합니다.

> Home Assistant 기본 `proximity` 통합이 “Zone 기준”인 것과 달리, 인접센서는 **엔티티 ↔ 엔티티(좌표 ↔ 좌표)** 간의 관계만 계산합니다.

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
- **새로고침 버튼(refresh)**  
  - 버튼을 누르면 즉시 현재 좌표를 다시 읽어 거리/근접을 재계산합니다.
  - (mobile_app 센서 자체를 강제로 업데이트하는 기능이 아니라, “현재 HA에 들어온 좌표 값”을 즉시 재계산합니다.)
- **안정성 옵션**
  - 디바운스: `debounce_seconds` (잦은 업데이트 묶음 처리)
  - 정확도 필터: `gps_accuracy` / `accuracy` / `horizontal_accuracy` 속성이 있으면 `max_accuracy_m` 기준으로 필터링
- **이벤트(Event) 발행**
  - `member_adjacency_enter` : 근접으로 바뀌는 순간
  - `member_adjacency_leave` : 비근접으로 바뀌는 순간

---

## Integration icon (mobile_app 아이콘 적용)

Home Assistant의 **통합(Integration) 카드 아이콘**은 `brands.home-assistant.io`의 브랜드 에셋을 사용합니다.  
커스텀 통합에서 “다른 통합(mobile_app)의 아이콘을 그대로 참조”하는 설정은 지원되지 않기 때문에, 인접센서의 통합 아이콘을 mobile_app과 동일하게 보이게 하려면 **brands에 인접센서용 아이콘을 동일 이미지로 등록(PR)** 해야 합니다.

- 목표: 인접센서 통합 아이콘이 `mobile_app` 아이콘과 동일하게 표시
- 방식: `custom_integrations/member_adjacency/` 경로에 mobile_app과 동일한 PNG 에셋 등록

(원하면 PR용 폴더/파일 구성도 같이 만들어 드릴 수 있습니다.)

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
   - 기본적으로 `*_geocoded_location` 센서가 목록에 표시/추천됩니다.
3. 임계값/옵션 입력 후 완료

---

## Supported coordinate formats

아래 중 하나면 동작합니다.

- `attributes.Location == [lat, lon]` (권장)
- `attributes.latitude` 와 `attributes.longitude`
- state 가 `"lat,lon"` 문자열

---

## Entities created (per A-B pair)

A-B 한 쌍을 추가하면, 해당 쌍은 **하나의 기기(Device)** 로 묶여 생성되며 아래 엔티티들이 포함됩니다.

- `sensor.member_adjacency_<pair>` : 거리 (m/km 자동 전환 또는 m 고정)
- `binary_sensor.member_adjacency_<pair>_proximity` : 근접 여부(on/off)
- `sensor.member_adjacency_<pair>_bucket` : 거리 구간
- `button.member_adjacency_<pair>_refresh` : 새로고침(즉시 재계산)

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
