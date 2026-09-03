# 인접센서 로컬 브랜드 자산

인접센서의 Home Assistant 브랜드 이미지는 통합 패키지 내부의 다음 경로에 포함됩니다.

```text
custom_components/member_adjacency/brand/
├─ icon.png
├─ icon@2x.png
├─ dark_icon.png
├─ dark_icon@2x.png
├─ logo.png
├─ logo@2x.png
├─ dark_logo.png
└─ dark_logo@2x.png
```

## 파일 규격

- `icon.png`, `dark_icon.png`: 256×256 투명 PNG
- `icon@2x.png`, `dark_icon@2x.png`: 512×512 투명 PNG
- `logo.png`, `dark_logo.png`: 423×128 투명 PNG
- `logo@2x.png`, `dark_logo@2x.png`: 846×256 투명 PNG

기본 아이콘은 두 위치 엔티티와 근접 관계를 두 개의 사람형 위치 핀, 연결점, 무선 신호로 표현합니다. 가로형 로고는 동일한 심볼과 `인접센서 / MEMBER ADJACENCY` 워드마크를 함께 사용합니다.

Home Assistant 2026.3 이상에서는 로컬 Brands Proxy API가 이 통합 내부 자산을 제공하므로 외부 개인 Brands 저장소를 런타임 원본으로 사용하지 않습니다.
