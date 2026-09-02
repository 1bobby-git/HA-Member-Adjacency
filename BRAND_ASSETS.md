# 인접센서 로컬 브랜드 자산

인접센서의 Home Assistant 기본 아이콘은 다음 경로에 통합 패키지와 함께 포함됩니다.

```text
custom_components/member_adjacency/brand/
├─ icon.png
├─ icon@2x.png
├─ dark_icon.png
└─ dark_icon@2x.png
```

새 아이콘은 두 위치 엔티티를 사람형 위치 핀으로 표현하고, 연결점과 무선 신호를 이용해 거리 및 근접 관계를 나타냅니다.

- `icon.png`, `dark_icon.png`: 256×256 투명 PNG
- `icon@2x.png`, `dark_icon@2x.png`: 512×512 투명 PNG
- 라이트·다크 화면에서 동일한 색상 체계를 사용합니다.
- 32px 축소 표시에서도 두 위치 핀과 근접 신호가 구분되도록 굵은 실루엣과 높은 대비를 적용했습니다.

Home Assistant가 로컬 Brands Proxy API를 지원하는 환경에서는 통합 내부 자산을 직접 사용하므로 외부 브랜드 저장소에만 의존하지 않습니다.
