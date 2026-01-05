# Member Adjacency Distance (Home Assistant Custom Integration)

두 개의 위치(좌표) 엔티티 사이의 거리를 **미터(m)** 로 계산하는 센서를 생성합니다.
주로 Home Assistant `mobile_app` 통합의 `*_geocoded_location` 센서(속성 `Location = [lat, lon]`)를 대상으로 사용합니다.

## Features
- 거리 센서: meters (device_class: distance, state_class: measurement)
- 이벤트 기반 업데이트(두 엔티티 상태 변화 시 즉시 갱신)
- 속성 `proximity`: 임계값(m)보다 가까우면 `true`

## Supported coordinate sources
아래 중 하나만 만족하면 됩니다.
- `attributes.Location == [lat, lon]`
- `attributes.latitude` & `attributes.longitude`
- 상태(state)가 `"lat,lon"` 문자열

## Install via HACS (Custom repository)
1. HACS → 오른쪽 상단 ⋮ → **Custom repositories**
2. 이 레포 URL 입력: `https://github.com/1bobby-git/ha-member-adjacency`
3. Type: **Integration**
4. 설치 후 Home Assistant 재시작

## Configuration
Home Assistant UI:
- 설정 → 기기 및 서비스 → 통합 추가 → **Member Adjacency Distance**
- Entity A / Entity B 선택
- (옵션) 센서 이름 / 아이콘 / 반올림 / 근접 임계값(m)

## Notes
- 두 엔티티가 좌표를 제공하지 않으면 센서 값은 `unknown`(native_value None)으로 표시됩니다.
