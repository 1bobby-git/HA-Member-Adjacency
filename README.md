# 인접센서 (Member Adjacency Distance)

두 개의 위치(좌표) 엔티티 사이 **거리 / 근접(Proximity)** 을 계산하는 Home Assistant 커스텀 통합입니다.

> Home Assistant 기본 `proximity` 통합이 "Zone 기준"인 것과 달리, 인접센서는 **엔티티 ↔ 엔티티** 관계만 계산합니다.

---

## Features

| 기능 | 설명 |
|------|------|
| **거리 센서** | 1000m 미만은 m, 이상은 km 자동 전환 |
| **근접 센서** | 히스테리시스 기반 on/off |
| **구간 센서** | very_near / near / mid / far / very_far |
| **지속시간 센서** | 근접 지속시간 (예: `1시간 20분`) |
| **업데이트 카운트** | 근접 진입 후 위치 업데이트 횟수 |
| **새로고침 버튼** | 소스 위치 업데이트 요청 + 즉시 재계산 |

---

## Install (HACS)

[![HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=1bobby-git&repository=HA-Member-Adjacency&category=integration)

---

## Setup

[![Setup](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=member_adjacency)

1. 설정 → 기기 및 서비스 → 통합 추가 → **인접센서**
2. Entity A / Entity B 선택
3. 임계값 설정 후 완료

---

## Events

| 이벤트 | 발생 시점 |
|--------|----------|
| `member_adjacency_enter` | 근접 진입 (1회) |
| `member_adjacency_leave` | 근접 이탈 (1회) |
| `member_adjacency_proximity_update` | 근접 상태에서 위치 업데이트마다 |

---

## 자동화 예제 (권장)

`member_adjacency_enter` 이벤트는 근접 진입 시 **정확히 1회만** 발생합니다.

```yaml
alias: "인접센서: 근접 알림"
triggers:
  - trigger: event
    event_type: member_adjacency_enter
    event_data:
      entity_a: sensor.member_a_geocoded_location
      entity_b: sensor.member_b_geocoded_location
actions:
  - action: notify.mobile_app_member_a
    data:
      title: "인접 알림"
      message: >
        {% set d = trigger.event.data.distance_m %}
        {% if d >= 1000 %}
          거리: {{ (d / 1000) | round(1) }}km
        {% else %}
          거리: {{ d | int }}m
        {% endif %}
```

더 많은 예제: [`examples/template.yaml`](examples/template.yaml)

---

## Version History

### v1.2.0 (2025-01-24)

**v1.1.8 대비 변경사항:**

| 구분 | v1.1.8 | v1.2.0 |
|------|--------|--------|
| 1회 알림 구현 | `input_boolean` 잠금 필요 | 이벤트/속성 기반으로 잠금 불필요 |
| 근접 업데이트 추적 | 없음 | `proximity_update_count` 속성 |
| 근접 업데이트 이벤트 | 없음 | `member_adjacency_proximity_update` |
| 중복 알림 방지 | 자동화에서 별도 처리 | 통합에서 기본 지원 |

**새 기능:**
- `proximity_update_count`: 근접 진입 후 위치 업데이트 횟수 (`1` = 첫 감지)
- `member_adjacency_proximity_update` 이벤트: 근접 중 위치 업데이트마다 발생
- `member_adjacency_enter` 이벤트에 `proximity_update_count` 추가

---

## License

MIT License
