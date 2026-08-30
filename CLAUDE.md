# PolyTwin

자동차 차체를 로봇팔이 자동 폴리싱하는 시뮬레이션의 **관제·설정 웹 콘솔**.
산업용 디지털 트윈 제품이고, 사용자는 공정 엔지니어다.
파라미터를 정하고 → 공정을 지켜보고 → 잘 된 설정을 저장하고 → 나중에 다시 꺼내 쓴다.

## 화면

| | 이름 | 성격 |
|---|---|---|
| ⓪ | 랜딩 | 브랜드. 인상을 만든다. 풀스크린 스크롤, 여백 과잉 |
| ① | 사전 설정 | 파라미터 슬라이더 + 3D 미리보기 |
| ② | 공정 모니터링 | 실시간 차트, 커버리지, 카메라 뷰 |
| ③ | 결과 분석 | 지표 6종, 히트맵 |
| ④ | 라이브러리 | 숙련공 데이터 저장·불러오기·비교 |

⓪은 인상, ①–④는 작업이다. **이 둘의 정보 밀도가 비슷해지면 둘 다 실패한 것이다.**

---

## 반드시 먼저 읽을 것

작업을 시작하기 전에 아래를 읽어라. 여기 있는 값과 다른 것을 쓰지 마라.

- **`DESIGN.md`** — 색·타이포·간격·모션 토큰. 실제 코드에서 감사해 확정한 값이다.
- **`ASSETS.md`** — 3D 모델·폰트 감축 기록과 재현 방법.
- **`AI티제거_지침서_폴리트윈_2026-08-27.md`** — 왜 이렇게 하는지에 대한 배경.
- **`UI목업_프롬프트_폴리트윈_2026-08-25.md`** — 원래 기획 의도와 화면별 요구사항.

---

## 절대 하지 않는 것

이 목록은 "AI가 만든 티"의 원인이다. 예외 없다.

- 보라/인디고 그라디언트 (`#6366F1` → `#A855F7` 계열)
- **Inter, Space Grotesk** — 이 프로젝트의 폰트는 Pretendard + IBM Plex Mono다
- 이모지 아이콘 (✨🚀⚡)
- 3열 균등 피처 카드 그리드
- `transition: all` — 속성을 명시하라
- 순수 회색(`#808080`, `#F5F5F5`) — 중립색에 청색을 5–10% 섞는다
- 장식용 `backdrop-blur` — 뒤에 실제로 뭔가 움직일 때만
- **12px 이상 라운드** — 이 제품은 2px / 4px만 쓴다
- 형용사 나열 카피 — "seamlessly", "powerful", "intuitive", "혁신적인", "직관적인"
- **`DESIGN.md`에 없는 색 추가** — 필요하면 기존 토큰으로 안 되는 이유를 먼저 적어라
- CSS에 리터럴 색상값 — `var(--토큰)`만

---

## 반드시 하는 것

- 숫자가 세로로 정렬되는 모든 곳에 `font-variant-numeric: tabular-nums`.
  실시간 수치에서 자릿수가 흔들리면 그것 하나로 아마추어가 된다.
- 한글 텍스트 컨테이너에 `word-break: keep-all`.
- 인터랙티브 요소에 `:focus-visible` — `outline: 2px solid var(--accent); outline-offset: 2px`.
- 애니메이션이 있으면 `@media (prefers-reduced-motion: reduce)`에서 정지.
- 다크 UI의 깊이는 **그림자가 아니라 선**으로. `1px solid var(--line)` + 배경 한 단계.
- **차트 값 갱신에 이징을 넣지 마라.** 값은 즉시, 형태만 부드럽게.

---

## 3D

```js
// 이 셋은 빼먹으면 즉시 티가 난다
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.outputColorSpace = THREE.SRGBColorSpace;
scene.environment = pmrem.fromScene(envScene, 0.03).texture;  // 없으면 금속이 금속이 아니다
```

- **형상보다 조명이 중요하다.** 키 라이트 1 + 좌우 림 라이트 2, 강한 명암 대비.
- 모델은 `assets/models/*.opt.glb` (meshopt 압축). `MeshoptDecoder`를 반드시 연결:
  ```js
  new GLTFLoader().setMeshoptDecoder(MeshoptDecoder)
  ```
- 카메라는 **바운딩 스피어 기준으로 자동 프레이밍**하라. 모델마다 스케일이
  3자릿수 넘게 차이난다(샌딩킷 0.003 단위, 차체 27 단위). 고정 좌표를 쓰면 안 된다.
- 무광 → 유광 스캔은 `material.onBeforeCompile`로 `roughnessFactor`를
  0.82 ↔ 0.14 보간. 동작하는 구현이 `asset-check.html`에 있다 — 거기서 복사해라.
- bloom은 `strength` 0.25 이하. 넘어가면 즉시 게임 UI가 된다.

---

## 성능 예산

| 항목 | 예산 |
|---|---|
| 3D 모델 합계 | < 3 MB |
| 폰트 | < 2 MB |
| 전체 최초 로드 | < 8 MB |
| LCP | < 2.5 s |

**자산을 base64로 HTML에 박지 마라.** 그것 때문에 파일이 89 MB가 됐고
되돌리는 데 이 문서 전체가 필요했다. 자세한 내용은 `ASSETS.md`.

---

## 검수

```bash
python -m http.server 8000
# → http://localhost:8000/asset-check.html
```

`asset-check.html`은 압축 모델을 원본과 나란히 비교하는 도구다.
3D를 건드렸으면 여기서 확인하고 넘어가라. `fetch`를 쓰므로 `file://`로는 안 열린다.

---

## 작업 방식

- **한 번에 한 화면.** 5화면을 동시에 시키면 품질이 떨어진다.
- **층별로 패스를 돈다.** 1차 구조 → 2차 타이포 → 3차 모션 → 4차 디테일.
  한 번에 다 고치면 전부 어중간해진다.
- 화면을 만든 뒤에는 **새 세션에서 비평시켜라.**
  "AI가 만든 티가 나는 부분 10개를 지적하고 각각 구체적 CSS 수정안을 달아라. 칭찬 금지."

---

## 디렉터리

```
assets/models/   압축 모델 (_orig/ 는 비교용, 배포 제외)
assets/fonts/    Pretendard 서브셋
assets/vendor/   three.js r169 + 애드온 + MeshoptDecoder
src/             번들에서 풀어낸 원본 소스 (참고용)
_backup_2026-08-27/   작업 전 백업 (배포 제외)
```
