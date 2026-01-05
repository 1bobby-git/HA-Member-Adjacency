# 인접센서 (Member Adjacency Distance)

두 개(또는 하나의 기준 + 여러 대상)의 위치(좌표) 엔티티 사이 **거리/근접(Proximity)** 을 계산하는 Home Assistant 커스텀 통합입니다.  
주로 `mobile_app` 통합에서 제공되는 `*_geocoded_location` 센서를 대상으로 사용합니다.

> 이 통합은 Home Assistant 기본 `proximity`(Zone 기준)와 달리, **엔티티 ↔ 엔티티(좌표 ↔ 좌표)** 거리/근접만 다룹니다.

---

## 핵심 기능

### 1) 기준(A) + 여러 대상(B) 지원
- 기준 센서 1개(Anchor A) + 대상 센서 여러 개(Targets B)를 선택하면,
  대상 수에 맞춰 **여러 엔티티가 자동 생성**됩니다.

### 2) 거리 단위 자동 전환 (m / km)
- 1000m 미만: **m**
- 1000m 이상: **km**
- 옵션 `force_meters`를 켜면 항상 **m 고정**

### 3) Proximity(근접) 판단 + 히스테리시스
- `entry_threshold_m` 이하로 들어오면 **근접(true)**
- `exit_threshold_m` 이상으로 벗어나면 **근접(false)**
- 경계값 근처에서 true/false가 깜빡이는 현상을 줄입니다.

### 4) binary_sensor 제공 (자동화에 최적)
- `proximity`를 속성 템플릿으로 쓰지 않아도 되도록
  **Binary Sensor 엔티티**를 별도로 생성합니다.

### 5) 이벤트 발행 (진입/이탈 트리거)
- 임계값 진입/이탈 시 이벤트를 fire 합니다.
  - `member_adjacency_enter`
  - `member_adjacency_leave`
  - `member_adjacency_any_enter`
  - `member_adjacency_any_leave`

### 6) 안정성 옵션
- 디바운스(연산 과다 방지): `debounce_seconds`
- 정확도 필터: 센서 속성에 `gps_accuracy` / `accuracy` / `horizontal_accuracy`가 있으면,
  `max_accuracy_m`보다 큰 경우 계산을 무시합니다.

### 7) 추가 센서
- 방위각(Bearing, A→B): 0~359°
- 거리 구간(Bucket): `very_near / near / mid / far / very_far`
- 최근접 대상/거리 요약 엔티티 제공

---

## 설치 (HACS)

1. HACS → Integrations → 우측 상단 ⋮ → Custom repositories  
2. Repository: `https://github.com/1bobby-git/HA-Member-Adjacency`  
3. Category: Integration  
4. 설치 후 Home Assistant 재시작

---

## 설정 (Setup)

1. 설정 → 기기 및 서비스 → 통합 추가 → **인접센서**
2. 기준(A) 1개 선택
3. 대상(B) 여러 개 선택
   - 기본적으로 `*_geocoded_location` 센서가 목록에 표시/추천됩니다.
4. 임계값/옵션 설정

### 지원하는 좌표 형태
아래 중 하나면 동작합니다.
- `attributes.Location == [lat, lon]` (권장)
- `attributes.latitude` & `attributes.longitude`
- state가 `"lat,lon"` 문자열

---

## 설정 옵션 설명

- `threshold_preset`
  - 50 / 100 / 200 / 500 / 1000 / custom
- `entry_threshold_m`
  - 진입 임계값 (이 값 이하이면 proximity=true)
- `exit_threshold_m`
  - 이탈 임계값 (이 값 이상이면 proximity=false)
  - exit는 entry보다 크거나 같아야 함
- `debounce_seconds`
  - 위치가 자주 바뀌는 경우 연산 폭주 방지
- `max_accuracy_m`
  - 0이면 정확도 무시
  - 값이 있으면, accuracy 속성이 이 값보다 큰 경우 계산 생략
- `force_meters`
  - 단위를 항상 m로 고정 (자동 km 전환 비활성화)

---

## 생성되는 엔티티

### A) 요약(Summary) 센서
- `sensor.member_adjacency` : 최근접 거리(단위 자동 전환 또는 m 고정)
- `sensor.member_adjacency_nearest` : 최근접 대상 엔티티 ID

요약 센서 속성 예시:
- `anchor`
- `nearest_target`
- `distance_m`, `distance_km`
- `any_proximity`

### B) 대상(B)별 센서 (Targets)
대상 엔티티가 예를 들어 `sensor.minnie_geocoded_location` 이면 object_id 기준으로 아래가 생성됩니다.
- `sensor.member_adjacency_<target>_distance` : 거리
- `sensor.member_adjacency_<target>_bearing` : 방위각(°)
- `sensor.member_adjacency_<target>_bucket` : 구간(very_near/near/mid/far/very_far)

거리 센서 속성 예시:
- `distance_m`, `distance_km`
- `bearing_deg`
- `bucket`
- `proximity`
- `last_changed`, `last_entered`, `last_left`

### C) Binary Sensors (Proximity)
- `binary_sensor.member_adjacency_proximity` : 대상들 중 하나라도 근접이면 true (any_proximity)
- `binary_sensor.member_adjacency_<target>_proximity` : 대상별 근접 true/false

---

## 이벤트(Event) 상세

근접 상태 변화 시 아래 이벤트가 발생합니다.

### 1) 대상별 진입/이탈
- `member_adjacency_enter`
- `member_adjacency_leave`

payload 예:
- `anchor`
- `target`
- `distance_m`
- `entry_threshold_m`
- `exit_threshold_m`

### 2) 전체(any) 진입/이탈
- `member_adjacency_any_enter`
- `member_adjacency_any_leave`

payload 예:
- `anchor`
- `any_proximity`
- `nearest_target`
- `nearest_distance_m`
- `entry_threshold_m`
- `exit_threshold_m`

---

## 자동화 활용 예

### 1) Binary Sensor 기반 (추천)
- 조건: `binary_sensor.member_adjacency_proximity == on`
- 액션: 알림/조명/문열림 등

### 2) 이벤트 기반 트리거
- 트리거: 이벤트 `member_adjacency_any_enter`
- 액션: “누군가 근접 진입” 알림

---

## 주의 / 제한

- 계산은 선택한 엔티티의 속성/상태에 포함된 좌표를 사용합니다.
- 좌표가 일시적으로 누락되거나 정확도 필터에 걸리면 값이 `unknown`이 될 수 있습니다.
- 엔티티 ID는 이미 생성된 경우 레지스트리 정책에 따라 `_2` 등이 붙을 수 있습니다.

---

## 로그 디버그

`configuration.yaml`:
    logger:
      default: info
      logs:
        custom_components.member_adjacency: debug
