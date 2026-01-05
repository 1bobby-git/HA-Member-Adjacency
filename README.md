# 인접센서 (Member Adjacency Distance)

두 개의 위치(좌표) 엔티티 사이 **거리 / 근접(Proximity)** 을 계산하는 Home Assistant 커스텀 통합입니다.  
주로 `mobile_app` 통합의 `*_geocoded_location` 센서(속성 `Location=[lat, lon]`)를 대상으로 사용합니다.

> Home Assistant 기본 `proximity`(Zone 기준)와 다르게, 이 통합은 **엔티티 ↔ 엔티티(좌표 ↔ 좌표)** 관계만 계산합니다.

---

## 주요 기능

- **거리 센서**: 두 엔티티 간 거리 (1000m 미만: m / 1000m 이상: km 자동 전환, 옵션으로 m 고정 가능)
- **근접(Binary Sensor)**: 임계값 이내면 `on` (true)
  - 히스테리시스 적용:
    - `entry_threshold_m` 이하로 들어오면 on
    - `exit_threshold_m` 이상으로 벗어나면 off
- **구간 센서**: 거리 구간(very_near / near / mid / far / very_far)
- **새로고침 버튼(Button)**: 버튼 클릭 시 즉시 위치를 다시 읽고 재계산
- **정확도 필터/디바운스**:
  - `gps_accuracy`/`accuracy`/`horizontal_accuracy`가 있으면 `max_accuracy_m` 기준으로 필터링
  - `debounce_seconds`로 잦은 업데이트를 묶어서 계산
- **이벤트 발행**:
  - `member_adjacency_enter` (근접 진입)
  - `member_adjacency_leave` (근접 이탈)

---

## 아이콘(요청 반영)

- 거리: `mdi:arrow-left-right`
- 근접: `mdi:map-marker-circle`
- 구간: `mdi:map-marker-distance`
- 새로고침 버튼: `mdi:refresh`

---

## 설치 (HACS)

1. HACS → Integrations → 우측 상단 ⋮ → Custom repositories
2. Repository: `https://github.com/1bobby-git/HA-Member-Adjacency`
3. Category: Integration
4. 설치 후 Home Assistant 재시작

---

## 설정 (Setup)

1. 설정 → 기기 및 서비스 → 통합 추가 → **인접센서**
2. Entity A / Entity B 선택
   - 기본적으로 `*_geocoded_location` 센서가 목록에 표시/추천됩니다.
3. 옵션 설정
   - `entry_threshold_m`, `exit_threshold_m`
   - `debounce_seconds`
   - `max_accuracy_m`
   - `force_meters`

### 지원하는 좌표 형태
아래 중 하나면 동작합니다.
- `attributes.Location == [lat, lon]` (권장)
- `attributes.latitude` & `attributes.longitude`
- state가 `"lat,lon"` 문자열

---

## 생성되는 엔티티 (A-B 1쌍당)

- `sensor.member_adjacency_<pair>` : 거리 (m/km 자동 전환 또는 m 고정)
- `binary_sensor.member_adjacency_<pair>_proximity` : 근접 여부
- `sensor.member_adjacency_<pair>_bucket` : 구간
- `button.member_adjacency_<pair>_refresh` : 새로고침

또한 설정한 A-B 쌍은 **하나의 기기(Device)** 로 묶이며, 위 엔티티들이 그 기기에 포함됩니다.

---

## Proximity(근접) 활용

- 자동화 조건으로 `binary_sensor ... == on` 을 사용하면 쉽게 “임계값 이내 접근”을 트리거로 활용할 수 있습니다.
- 히스테리시스로 경계 근처에서 켜졌다/꺼졌다 반복되는 현상을 완화합니다.

---

## 이벤트(Event) 활용

- `member_adjacency_enter`: 근접으로 바뀌는 순간 발생
- `member_adjacency_leave`: 비근접으로 바뀌는 순간 발생

payload 예:
- `entity_a`, `entity_b`
- `distance_m`
- `entry_threshold_m`, `exit_threshold_m`

---

## 로그 디버그

`configuration.yaml`:
    logger:
      default: info
      logs:
        custom_components.member_adjacency: debug
