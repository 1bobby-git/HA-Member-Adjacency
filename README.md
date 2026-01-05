# 인접센서 (Member Adjacency Distance)

두 개의 위치(좌표) 엔티티 사이의 거리를 계산하는 Home Assistant 커스텀 통합입니다.  
주로 `mobile_app` 통합에서 제공되는 `*_geocoded_location` 센서를 대상으로 사용합니다.

---

## 기능 (Features)

- 두 엔티티 간 거리 센서 생성
  - 1000m 미만: **m**
  - 1000m 이상: **km** (자동 전환)
  - 항상 속성에 `distance_m`, `distance_km`를 함께 제공
- `proximity` 속성 제공 (true/false)
  - **Proximity = 두 위치가 임계값(threshold) 이하로 가까우면 true**
  - 활용 예: 자동화(Automation) 조건으로 `proximity == true` 사용

---

## 설치 (HACS)

[![Open your Home Assistant instance and show the HACS repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=1bobby-git&repository=HA-Member-Adjacency&category=integration)

1. HACS → Integrations → 우측 상단 ⋮ → Custom repositories  
2. Repository: `https://github.com/1bobby-git/HA-Member-Adjacency`  
3. Category: Integration  
4. 설치 후 Home Assistant 재시작

---

## 설정 (Setup)

[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=member_adjacency)

1. 설정 → 기기 및 서비스 → 통합 추가 → **인접센서**
2. Entity A / Entity B 선택
   - 기본적으로 `mobile_app`의 `*_geocoded_location` 센서가 자동 추천됩니다.
   - 선택 목록도 `*_geocoded_location` 센서만 표시되도록 제한됩니다.
3. Proximity threshold (m) 입력
   - 예: 500 → 500m 이내면 `proximity: true`

---

## 지원하는 좌표 형태

아래 중 하나면 동작합니다.

- `attributes.Location == [lat, lon]`  (권장: 질문에서 사용하던 형태)
- `attributes.latitude` 와 `attributes.longitude`
- state 가 `"lat,lon"` 문자열

---

## 센서 출력 예시

- 상태(state): 거리 값 (단위: m 또는 km 자동 전환)
- 속성(attributes):
  - `entity_a`, `entity_b`
  - `distance_m`, `distance_km`
  - `proximity_threshold_m`
  - `proximity` (threshold 이하이면 true)
  - `coords_a`, `coords_b`

---

## Proximity 활용 예 (Automation)

- 조건: `sensor.인접센서`의 `proximity` 속성이 `true`일 때 실행

(예: 가족이 500m 이내로 접근하면 알림, 문열기 등)
