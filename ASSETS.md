# PolyTwin 자산 감사 · 감축 기록

**측정일** 2026-08-27 · **도구** `@gltf-transform/cli`, `fonttools` + `brotli`
**검수** `asset-check.html` (로컬 서버에서 열 것)

---

## 1. 무엇이 문제였나

배포 HTML 8개가 **총 89 MB**였다. 원인은 전부 base64로 단일 HTML에 박힌 자산이다.

| 파일 | 크기 |
|---|---|
| `polytwin-landing.html` | 22.9 MB |
| `PolyTwin Console.html` | 20.4 MB |
| `PolyTwin Landing 2.html` | 9.6 MB |
| `PolyTwin.html` (통합본) | 8.1 MB |
| 나머지 4개 | 12.7 MB |

번들은 **중첩**돼 있었다. `PolyTwin.html` 안에 4개 페이지가 gzip+base64로 들어 있고,
그 각각이 다시 자기 매니페스트를 가진 번들이었다. 재귀로 풀어야 실체가 보인다.

### 해체 결과

```
고유 파일 39개 / 중복으로 낭비된 용량 31.6 MB
고유 자산 합계 46.68 MB
```

| 종류 | 개수 | 용량 |
|---|---|---|
| GLB 3D 모델 | 3 | 28.68 MB |
| 폰트 woff | 9 | 9.60 MB |
| 폰트 woff2 | 15 | 6.66 MB |
| 스크립트 | 12 | 1.73 MB |

**같은 자산이 파일마다 중복 포함돼 31.6 MB가 그냥 버려지고 있었다.**

---

## 2. 3D 모델

### 진단

세 모델 모두 **Blender에서 뽑은 원본 그대로**였다. 텍스처 0장, 압축 확장 없음,
양자화 없음. 순수 float32 지오메트리 91만 삼각형.

> **이름이 뒤바뀌어 있었다.** 22 MB짜리를 차체로 알고 있었으나 내부 노드명은
> `m0609_SL_runtime` — SL 로봇이다. 차체는 4 MB짜리(`tc`, `mi_car_paint_phen1SG`
> 등 car_paint 재질 11종)다. `assets/models/`에서 바로잡았다.

### 감축 결과 (실측)

| 모델 | 삼각형 | 원본 | A: 양자화 | B: +간략화 50% | **C: +meshopt** |
|---|---|---|---|---|---|
| 로봇 SL | 641,724 | 22.19 MB | 15.22 MB | 8.72 MB | **1.66 MB** |
| 차체 | 163,636 | 4.00 MB | 1.57 MB | 0.79 MB | **0.26 MB** |
| 샌딩 킷 | 111,387 | 2.50 MB | 1.10 MB | 0.68 MB | **0.23 MB** |
| **합계** | 916,747 | **28.69 MB** | 17.89 MB | 10.19 MB | **2.15 MB** |

**28.69 MB → 2.15 MB (−92.5%)**

### 어느 것을 쓸까

- **C(meshopt)를 쓴다.** 런타임에 `MeshoptDecoder`(32 KB)가 필요하지만 이미
  `assets/vendor/meshopt_decoder.mjs`에 넣어뒀고 GLTFLoader가 지원한다.
- A(양자화)는 디코더가 전혀 필요 없다. 어떤 이유로든 meshopt를 못 쓰면 이걸로.
- B/C는 삼각형을 50% 줄인다. **차체는 육안 차이가 없었다.** 로봇 SL은
  `asset-check.html`에서 직접 확인할 것 — 관절부가 뭉개지면 비율을 0.7로 올려라.

### 재현

```bash
GT="npx --yes @gltf-transform/cli"
$GT weld     in.glb  t1.glb
$GT simplify t1.glb  t2.glb --ratio 0.5 --error 0.001
$GT meshopt  t2.glb  out.glb --level high
```

### 런타임 연결

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from './assets/vendor/meshopt_decoder.mjs';

const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const gltf = await loader.loadAsync('./assets/models/car.opt.glb');
```

---

## 3. 폰트

### 진단

**Pretendard 9 웨이트(100–900)를 woff2 + woff 두 벌씩, 24개 파일 16.26 MB.**
한글 전체 글리프가 들어 있어 웨이트당 woff2 0.75 MB, woff 1.07 MB다.

두 가지가 동시에 낭비였다.
1. `.woff`는 woff2의 폴백일 뿐인데 9개 전부 실려 있었다 — **9.6 MB 순수 낭비.**
   woff2를 못 읽는 브라우저는 2016년 이전 것뿐이다.
2. 9 웨이트를 다 쓰고 있지 않다.

### 감축 결과 (실측)

| 방식 | 웨이트 | 글리프 | 크기 | 감축 |
|---|---|---|---|---|
| 원본 (번들 전체) | 9 × 2포맷 | 한글 전체 | 16.26 MB | — |
| **`.subset`** | 300/500/700 | 실제 쓰는 928자 | **192 KB** | −98.8% |
| `.full-ko` | 300/500/700 | 한글 11,172자 전체 | 1.75 MB | −89.2% |

### 어느 것을 쓸까

- **`.full-ko`를 권한다.** 1.75 MB면 예산 안이고, **앞으로 어떤 한글을 써도 깨지지 않는다.**
- `.subset`(192 KB)은 현재 텍스트에 등장한 928자만 들어 있다. 카피를 한 글자라도
  바꾸면 그 글자가 두부(□)로 나온다 — 실제 배치는 `--f-sans: "Pretendard", "Pretendard Full"`
  로 폴백을 걸어 두부 대신 **full-ko 1.75 MB 가 통째로 내려오는** 쪽으로 실패한다.
  **카피를 고쳤으면 `python scripts/font-subset.py` 를 돌려라.** (2026-08-31 검수에서
  103자 누락 → 매 화면 1.75 MB 추가 다운로드를 확인하고 재생성했다.)
  주의: `full-ko` 는 한글 전용이라 `·–—…°µ×` 기호 글리프가 없다. 스크립트는 기존 서브셋을
  공여자로 합쳐 기호를 유지한다 — 서브셋 파일을 지우고 처음부터 만들면 기호가 빠진다.

```css
@font-face {
  font-family: Pretendard; font-weight: 300; font-display: swap;
  src: url("./assets/fonts/Pretendard-300.full-ko.woff2") format("woff2");
}
/* 500, 700 동일 */
```

---

## 4. 스크립트

`three.js r169`이 **비압축 1.24 MB**로 들어 있다. 압축본은 약 600 KB다.
번들러가 gzip을 걸고 있으므로 전송량은 그보다 작지만, 파싱 비용은 그대로다.

- 지금 구조를 유지한다면 최소한 minify된 `three.module.min.js`로 교체.
- `EffectComposer`/`BufferGeometryUtils` 등 안 쓰는 애드온이 실려 있는지 확인할 것.

---

## 5. 종합

| 항목 | 이전 | 이후 | 예산 |
|---|---|---|---|
| 3D 모델 | 28.69 MB | **2.15 MB** | < 3 MB ✅ |
| 폰트 | 16.26 MB | **1.75 MB** | < 2 MB ✅ |
| 스크립트 | 1.73 MB | 1.73 MB | < 1 MB ⚠️ |
| 중복 자산 | 31.6 MB | **0** | 0 ✅ |
| **고유 자산 합계** | **46.68 MB** | **≈ 5.6 MB** | < 8 MB ✅ |

**−88%.** 남은 과제는 three.js minify와, 자산을 HTML에서 떼어내 별도 파일로
서빙하도록 빌드를 바꾸는 것이다.

---

## 6. 디렉터리

```
assets/
  models/
    car.opt.glb              0.26 MB   ← 차체
    robot_sl.opt.glb         1.66 MB   ← SL 로봇
    sanding_kit.opt.glb      0.23 MB
    _orig/                  28.69 MB   ← 원본. 비교 검수용, 배포에서 제외
  fonts/
    Pretendard-{300,500,700}.full-ko.woff2   1.75 MB  ← 권장
    Pretendard-{300,500,700}.subset.woff2    192 KB   ← 실사용 (scripts/font-subset.py 로 재생성)
  vendor/
    three.module.js, meshopt_decoder.mjs,
    loaders/GLTFLoader.js, controls/OrbitControls.js,
    utils/BufferGeometryUtils.js
src/                          ← 번들에서 풀어낸 원본. 참고용
_backup_2026-08-27/           ← 작업 전 HTML·MD 전체 백업 (71 MB)
```

**배포 전 삭제:** `assets/models/_orig/`, `src/`, `_backup_2026-08-27/`

---

## 7. 검수 방법

`asset-check.html`은 `fetch`를 쓰므로 **`file://`로 열면 동작하지 않는다.**

```bash
cd "해커톤 UI"
python -m http.server 8000
# → http://localhost:8000/asset-check.html
```

- **모델 × 버전**을 번갈아 눌러 압축본과 원본의 실루엣을 비교한다.
- **와이어프레임**을 켜면 어느 부위의 삼각형이 줄었는지 보인다.
- **스캔 위치** 슬라이더로 무광→유광 전환을 직접 확인한다.
  이 셰이더가 랜딩 히어로에 그대로 들어갈 것이다 (`onBeforeCompile`로
  `roughnessFactor`를 스캔면 기준으로 0.82 ↔ 0.14 보간).
- 좌측 수치(파일 크기 / 삼각형 / 드로우 콜 / 로드 ms)는 실측값이다.

> 뷰어 안의 fps는 무시해도 된다. 헤드리스 검증 때 소프트웨어 렌더러(SwiftShader)로
> 측정된 값이 20 fps대였을 뿐, 실제 GPU에서는 훨씬 높다.

---

## 영상 (2026-08-31 실측)

| 파일 | 크기 | 쓰는 곳 |
|---|---|---|
| `polishing.webm` | 17.7 MB | `sub.html?p=polishing` 히어로 · `?p=media` |
| `hero.mp4` | 9.4 MB | `index.html` 히어로 · `?p=media` |
| `pick-place.mp4` | 2.8 MB | `?p=pickplace` 이송 실행 · `?p=media` |

영상은 `preload="metadata"` 라서 처음엔 메타데이터만 받는다. 다만 sub.html 은
`IntersectionObserver` 로 화면에 들어온 영상을 자동 재생하고(2058행), 폴리싱 페이지는
그 영상이 첫 화면에 있다. 그래서 실제로 흘러 들어온다.

**transferSize 실측 (Range 지원 서버, 로드 후 4초)**

| 화면 | 무게 | DCL |
|---|---|---|
| `index.html` | 6.54 MB | 386 ms |
| **`sub.html?p=polishing`** | **14.58 MB** | 164 ms |
| `PolyTwin Console.html` | 2.86 MB | 59 ms |
| `monitor.html` | 2.98 MB | 173 ms |
| `PolyTwin Save.html` | 0.89 MB | 87 ms |
| `PolyTwin Library.html` | 1.51 MB | 37 ms |

**sub.html 만 8 MB 예산을 넘는다.** 12.4 MB 가 `polishing.webm` 이다.
20초 1210x666 화면 녹화가 17.7 MB면 약 7 Mbps — 화면 녹화치고 과하다.
VP9 1.5 Mbps 로 다시 인코딩하면 20초에 4 MB 안쪽으로 들어오고 그러면 예산에 든다.

```bash
# ffmpeg 가 이 환경에 없어 실행하지 못했다. 설치한 곳에서:
ffmpeg -i polishing.webm -t 20 -c:v libvpx-vp9 -b:v 1500k -crf 33 \
       -row-mt 1 -an polishing.opt.webm
```

재인코딩 전까지는 이 페이지가 무거운 채로 남는다. 자동 재생을 빼면 무게는
내려가지만 첫 화면에서 제품이 도는 걸 못 보게 되므로 그 교환은 하지 않았다.

---

## 그림 색 이동 — 청록 → 브랜드 연두 (2026-08-31)

액센트를 `#3E9DBE`(청록)에서 `#9BC33A`(로고 연두)로 바꾸면서, `sub.html` 의
설명 그림 23장이 혼자 옛 색으로 남았다. UI 는 연두인데 그림 속 선·차트·
와이어프레임은 청록이라 같은 화면 안에서 두 브랜드가 싸운다.

`scripts/recolor-cyan-to-lime.py` 로 옮겼다. **색상환을 통째로 돌리지 않는다** —
그러면 회청색 패널 테두리(`#232830`, 색상각 217°)와 '등록' 초록 체크까지 끌려간다.

- 색상각 **168–214°** 안에서만 동작. 구간 양 끝 8° 는 부드럽게 빠진다.
- 채도 0.24→0.38, 명도 0.16→0.28 구간에서 가중치를 매긴다.
  안티에일리어싱 경계 화소는 거의 안 건드리므로 테두리에 헤일로가 안 생긴다.
- 목표 색상각 78°, 원본 색상 변화는 0.25 배로 압축해 남긴다.
- **명도를 0.80 배 한다.** 같은 명도에서 연두는 청록보다 밝게 보인다.
  안 낮추면 선이 굵어지고 차트가 번진다. `#4FC3F7` → 약 `#9CC64A`.

| | |
|---|---|
| 옮긴 파일 | 19 장 (전체 화소의 0.2 – 7.0 % 가 이동) |
| 손대지 않은 파일 | `crop_ansys.webp` — ANSYS 접촉압 **무지개 컬러맵**이다. 돌리면 데이터가 거짓말이 된다<br>`wide_docs.webp` — 사실상 무채색<br>`crop_blindspot` · `crop_rl_asset` — 청록이 없다. 재인코딩하면 세대 손실만 남으므로 스크립트가 쓰기를 건너뛴다<br>`pdf_20_*.jpg` — 시안 화소 0.009 % |
| 용량 | 1.72 MB → **1.53 MB** (webp q86 재인코딩) |
| 원본 | `assets/img/_precyan_2026-08-31/` (배포 제외) |

되돌리려면 `_precyan_2026-08-31/*.webp` 를 `assets/img/` 로 복사하면 된다.

```bash
python scripts/recolor-cyan-to-lime.py   # _precyan_ 을 읽어 assets/img/ 에 쓴다. 반복 실행해도 누적되지 않는다
```

브라우저 캐시는 `sub.html` 의 `ASSET_V` 로 끊는다. 그림을 다시 손대면 이 값을 올려라.

---

## 그림 밝기 리프트 — 감마 1.55 (2026-08-31)

다크 리메이크 그림 23장이 너무 어두웠다. 실측하니 22장의 밝기 중앙값이
**0.02 – 0.09** 다. 페이지 배경 `--bg-void`(`#08090B`)가 0.003 이니 그림판이
사실상 배경과 같은 검정이고, 그림이 페이지 위에 얹힌 물체로 안 읽힌다.

**밝기를 곱하지 않는다.** 곱셈(= CSS `brightness()`)은 0.10 을 1.3 배 해봐야
0.13 이다. 감마로 아래쪽을 들어올려야 한다.

```
v' = v ** (1/1.55)          v = HSV 의 V (= RGB 최대 채널)
```

- RGB 셋을 같은 배율 `v'/v` 로 민다 → **색상각·채도가 정확히 보존된다.**
  ANSYS 무지개 컬러맵도 값이 색상각에 있으므로 데이터가 거짓말이 되지 않는다.
  (그래서 재색 스크립트와 달리 `crop_ansys.webp` 를 건너뛸 이유가 없다.)
- 배율 기준이 최대 채널이라 어떤 채널도 클리핑되지 않는다.
- 감마 곡선은 1.0 에 붙어 있어 흰 글자·하이라이트가 날아가지 않는다.
- **바닥을 보호하지 않는 것이 핵심이다.** 그림판이 `--bg-void` 에서
  `--bg-raised` 한 단계 위로 올라와야 그림이 페이지에서 떠오른다
  (CLAUDE.md — "다크 UI의 깊이는 그림자가 아니라 선으로, 배경 한 단계").
  순수 검정 배경(`wide_docs.webp`)은 `0 ** x = 0` 이라 저절로 검정으로 남는다.

감마 **1.9 이상은 쓰지 마라.** 채도가 그대로인 채 명도만 올라가 화면이
파르스름하게 뜬다. 약하게 가려면 1.35, 기본 1.55, 강하게 1.7.

| | |
|---|---|
| 처리 | 29 장 전부 (중앙값 > 0.35 인 그림은 자동으로 건너뛴다 — 현재 해당 없음) |
| 밝기 중앙값 | 0.056 → **0.140** (29장 평균) |
| 용량 | 1.92 MB → **2.22 MB** (webp q86 재인코딩, +300 KB) |
| 원본 | `assets/img/_prebright_2026-08-31/` (배포 제외) |

같은 날 늦게 `PH(...)` 자리에 넣은 생성 도해 6장도 여기에 포함된다. 처음에는
생성 결과가 기존보다 **밝게** 나올 줄 알고 리프트에서 빼려 했는데, 실제로는
중앙값 0.037–0.094 로 **더 어둡게** 나왔다. 그래서 6장도 `_prebright_` 에 넣고
같은 감마를 먹였다. 새 그림을 받으면 무조건 실측부터 하고 판단해라.

되돌리려면 `_prebright_2026-08-31/*.webp` 를 `assets/img/` 로 복사하면 된다.

```bash
python scripts/brighten-figures.py        # 기본 1.55
python scripts/brighten-figures.py 1.35   # 세기 조절. 항상 _prebright_ 원본에서 다시 굽는다 (누적 없음)
```

`ASSET_V` 를 `2026-08-31e` 로 올렸다.
