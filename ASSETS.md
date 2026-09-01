# PolyTwin 자산 감사 · 감축 기록

**측정일** 2026-08-27 · **도구** `@gltf-transform/cli`, `fonttools` + `brotli`
**검수** `appendix/tools/asset-check.html` (로컬 서버에서 열 것)

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
  `appendix/tools/asset-check.html`에서 직접 확인할 것 — 관절부가 뭉개지면 비율을 0.7로 올려라.

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
appendix/sourcecode/          ← 번들에서 풀어낸 원본. 참고용
appendix/backups/             ← 예전 HTML 버전 (37 MB)
```

**배포에서 제외됨(.vercelignore):** `frontend/assets/models/_orig/`, `appendix/`

---

## 7. 검수 방법

`appendix/tools/asset-check.html`은 `fetch`를 쓰므로 **`file://`로 열면 동작하지 않는다.**

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

## 차종 4종 — 벤츠·페라리·쏘나타 실모델 (2026-09-01)

① 사전 설정의 차종 선택기는 **셋이 Z4 하나를 색만 바꿔 쓰고 있었다.**
`setVehicle` 이 `car.opt.glb` 를 한 번 파스해 지오메트리를 공유하고 tint 만
갈아 끼웠다. 원본이 들어오는 대로 실모델로 바꿨고 넷이 됐다.

| 차종 | id | 자산 | 원본 | 삼각형 | 크기 |
|---|---|---|---|---|---|
| BMW Z4 | `z4` | `car.opt.glb` | `_orig/car.glb` 4.00 MB | 81,818 | **0.26 MB** |
| 벤츠 쿠페 | `coupe` | `benz.opt.glb` | `_orig/benz.obj` 13.9 MB | 90,074 | **0.35 MB** |
| 페라리 SF90 | `sf90` | `ferrari.opt.glb` | `_orig/ferrari_sf90_v146.obj` 553 MB | 90,461 | **0.35 MB** |
| 현대 쏘나타 | `sonata` | `sonata.opt.glb` | `_orig/2015-hyundai-sonata/` 75 MB | 89,893 | **0.41 MB** |

배포되는 모델 합계 **2.86 MB** — 3 MB 예산 안이다(`robot_sl.opt.glb` 는
`.vercelignore` 로 제외). 네 차종을 한꺼번에 받지는 않는다. `setVehicle` 이
고른 차종만 `loadCar` 하고 `_carLoads` 에 캐시하므로 **첫 화면은 z4 의
0.26 MB 만** 내려받는다.

> 처음에는 벤츠 176k · 페라리 155k 로 구웠다. 차가 넷이 되면서 예산을
> 넘어(3.49 MB) **셋 다 Z4 밀도(82k)로 다시 내렸다.** 육안 차이가 없다 —
> 뷰포트 안에서 차체가 1000px 을 넘지 않아 90k 면 실루엣이 남는다.
> 밀도를 차마다 다르게 두면 같은 화면에서 한 대만 각져 보이므로,
> **새 차를 넣을 때도 90k 내외로 맞춰라.**

### ① 에서 고른 차가 ② 로 넘어간다

`localStorage.polytwin_vehicle` 한 칸이다. ① 이 차종을 누를 때 쓰고,
② `monitor.html` 이 뜰 때 읽는다. `?vehicle=z4|coupe|sf90` 이 있으면
그게 이긴다 — 링크로 특정 차종을 열 때.

- **`polytwin_preset` 을 쓰지 않는다.** 그건 RL 검증을 저장해야 생기므로
  차종만 바꾸고 넘어가면 비어 있다.
- ① 은 다시 들어와도 마지막 차로 연다. `<polytwin-viewport>` 에는 `vehicle`
  attribute 가 없어 3D 는 항상 z4 로 뜨므로, `push()` 가 매번 `setVehicle` 을
  불러 맞춘다 (같은 id 면 즉시 돌아온다).
- **② 는 축을 스스로 맞춰야 한다.** 배치 코드가 'Z 가 전장, X 가 폭' 을
  전제하는데 페라리 원본은 X 가 전장이다. `carSize.x > carSize.z` 면 Y 로
  90도 돌린다 — ① 의 `loadCar` 가 하는 것과 같은 규칙이다.
- 하단 요약 줄에 차종을 적었다. 토막이 「차종 / · 셀 / · 로봇 / …」 로 끊기므로
  `i18n-app.js` 에 `차종` · `· 셀` 을 더했다(첫 토막이 `셀` 에서 `· 셀` 로 바뀐다).
  화면 글을 건드렸으면 `python scripts/i18n-app-check.py` 를 돌려라.

랜딩(`index.html`)의 히어로는 Z4 고정이다. 로그인 전 화면이라 차종 선택
맥락이 없고, 브랜드 인상이 브라우저에 남은 값에 따라 달라지면 안 된다.

### 재현 — OBJ 는 obj2gltf 로 들어오지 않는다

두 원본 모두 trimesh 가 뽑은 OBJ 다. 법선도 UV 도 없고 재질은 `mat_0` 하나뿐인데
`material.mtl` 은 같이 오지 않았다(경고만 나고 기본 재질로 진행된다).

벤츠(13.9 MB)는 `obj2gltf` 로 들어온다.

```bash
npx --yes obj2gltf -i _orig/benz.obj -o benz_raw.glb
```

**페라리(553 MB · 정점 6,940,401 · 삼각형 12,930,305)는 obj2gltf 로 못 연다.**
숫자를 전부 JS 배열에 담아서 힙을 넘긴다. `scripts/obj2glb.mjs` 가 파일을
줄 단위로 흘리면서 타입드 배열에 바로 쌓는다 — 553 MB 를 **9.5 초**에 읽는다.
검증은 벤츠를 두 방법으로 굽고 정점·삼각형·바운딩 박스가 일치하는 걸로 했다.

```bash
node --max-old-space-size=14336 scripts/obj2glb.mjs \n     frontend/assets/models/_orig/ferrari_sf90_v146.obj ferrari_raw.glb
```

### 감축 — 비율은 차마다 다르다

목표는 삼각형 **9만 내외**다. 기준선은 Z4(원본 163,636 → 81,818)이고,
원본 밀도가 네 자릿수 넘게 차이나므로 `--ratio` 를 그대로 쓰면 안 된다.
**비율이 아니라 결과 삼각형 수를 맞춰라.**

```bash
GT="npx --yes @gltf-transform/cli"
$GT weld benz_raw.glb b1.glb                              # 벤츠     353,236 tri
$GT simplify b1.glb bx.glb --ratio 0.255 --error 0.003
# 페라리 12,930,305 tri — 0.007 까지 내려야 9만이 된다. error 도 0.006 으로
# 풀어야 감축기가 오차 한계에 걸려 중간에 멈추지 않는다
$GT simplify f1.glb fx.glb --ratio 0.007 --error 0.006
$GT simplify s5.glb sx.glb --ratio 0.368 --error 0.003   # 쏘나타   244,341 tri
```

### 쏘나타는 텍스처와 실내가 들어 있었다

앞의 둘과 종류가 다른 자산이다 — BeamNG 계열 GLB 로 **48 MB 중 44 MB 가
텍스처**이고, 메시 210개·재질 35개에 엔진룸·시트·대시보드까지 들어 있다.

- **텍스처는 한 바이트도 안 쓰인다.** ①의 `loadCar` 도 ②도 재질을 자기
  `MeshPhysicalMaterial` 로 갈아 끼운다. 텍스처·UV·탄젠트를 떼면 48 MB → 4.05 MB.
- **실내·엔진은 뺀다.** 남겨도 차체 안에 갇혀 안 보이는데 삼각형의 44%(194,184)를
  먹는다. 그만큼을 외부 셸에 쓰는 게 낫다. 어느 재질을 뺄지는 **이름이 아니라
  재질별 바운딩 박스**로 골랐다 — 차체 밖까지 뻗는 `vehicle_dark_kg`(범퍼·몰딩)와
  `sonatablack` 은 이름만 보면 실내 같지만 남겨야 한다.

| 뺀 재질 | 삼각형 | 근거 (바운딩 박스) |
|---|---|---|
| `sunburst_engine.003` | 62,311 | z 0.61…1.73 — 보닛 아래 |
| `intlight` | 54,636 | x 0.20…0.79 · z 0.05…0.42 — 캐빈 안 |
| `aluminium` | 26,598 | 엔진·서스펜션 |
| `etk800_seats…beige` | 22,553 | 시트 |
| `torpedo_leather` | 13,101 | 대시보드·리어 선반 |
| `sunburst_main` | 8,921 | 섀시·플로어 |
| `midsize_mechanical.004` | 6,014 | 언더바디 |
| 스크린 3종 | 50 | 계기판·내비 |

떼고 나면 재질이 전부 같아진다 → `dedup` 이 하나로 합치고 `join` 이 메시
210개를 한 덩이로 묶는다. **드로우 콜 210 → 1.** `loadCar` 는 소스 메시마다
`THREE.Mesh` 를 하나씩 만들므로 이걸 안 하면 차 한 대가 210 드로우 콜이다.

```bash
node prep-sonata.mjs "2015 Hyundai Sonata.glb" s0.glb   # 실내 제거 + 텍스처/UV 제거
$GT prune s0.glb s1.glb && $GT dedup s1.glb s2.glb
$GT flatten s2.glb s3.glb && $GT join s3.glb s4.glb
$GT weld s4.glb s5.glb
```

### 법선은 감축 뒤에 굽는다

OBJ 에 `vn` 이 하나도 없다. 감축 **전에** 법선을 넣으면 감축기가 그 값을
보간해 뭉갠 법선이 남는다. 그래서 `scripts/bake-normals.mjs` 로 감축 결과에
면적 가중 스무스 법선을 새로 굽는다 — 외적을 정규화하지 않고 더하면
큰 면이 셰이딩을 지배해 도장면이 매끄럽게 읽힌다.

```bash
node scripts/bake-normals.mjs b2.glb b3.glb
$GT meshopt b3.glb benz.opt.glb --level high
```

법선을 굽지 않으면 파일이 100 KB 작아지고 `loadCar` 의
`if (!g.attributes.normal) g.computeVertexNormals()` 가 같은 값을 런타임에
만든다. 그래도 굽는 쪽을 골랐다 — `asset-check.html` 처럼 그 폴백이 없는
뷰어에서도 같은 형상이 나와야 한다.

### 축 — 손댈 것이 없었다

둘 다 Y-up 이다. 길이축만 다르다(벤츠 Z, 페라리 X). `loadCar` 가
`sz.x > sz.z` 일 때 Y 로 90도 돌리고 `CAR_LENGTH`(4.35 m)에 맞춰 스케일한 뒤
바닥 중앙으로 옮기므로 **자산 쪽에서 축을 맞출 필요가 없다.**

| | 원본 바운딩 박스 (m) | 길이축 |
|---|---|---|
| 벤츠 | 0.263 x 0.170 x 0.652 | Z (스케일 없음) |
| 페라리 | 4.719 x 1.166 x 1.989 | X (실척) |
| 쏘나타 | 1.890 x 1.381 x 4.373 | Z (실척) |

### 원본은 커밋하지 않는다

`_orig/` 는 원래 커밋하는 자리지만(car.glb 등 30 MB), 이번 원본들은
**1.7 GB** 다. `.gitignore` 에 `_orig/*.obj` · `_orig/ferrari.glb` ·
`_orig/2015-hyundai-sonata/` 를 넣었다.
배포에는 `_orig/` 전체가 이미 `.vercelignore` 로 빠진다.

> `frontend/assets/models/ferrari.glb`(1.04 GB · 페라리 원본을 그대로 구운 것)가
> **배포 루트에** 있었다. `_orig/` 로 옮겼다. 감축 안 된 모델을 `models/` 에
> 두면 `.vercelignore` 가 못 잡는다.

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

---

## 기획서 크롭 → 네이티브 도해 (2026-08-31)

**표를 그림으로 넣지 마라.** 그림에 구운 글자는 선택도 검색도 번역도 안 되고,
스크린리더가 못 읽고, `.p-fig img` 의 `max-height: 460px` 에 걸려 모바일에서
글자까지 같이 줄어든다. 기획서 크롭 29장 중 **애초에 그림일 이유가 없던 10장**을
`sub.html` 의 `FIGS` 마크업으로 옮겼다.

| 옮긴 그림 | 새 도해 키 | 내용 |
|---|---|---|
| `crop_security.webp` | `logsplit` | 이벤트 로그 / 스텝 로그 표 2개 |
| `crop_rl_asset.webp` | `rlasset` | 조합별 전문가 점수·판정 표 |
| `crop_rbac.webp` | `rbac` | 역할 × 권한 격자 |
| `crop_rl_env.webp` | `rlenv` | 3종 × 4단계 × 4단계 = 48 조합 |
| `crop_rl_policy.webp` | `rlpolicy` | 정책·환경 순환과 보상 함수 |
| `crop_rl_eval.webp` | `rleval` | 전문가 평가 4항목 |
| `crop_deburr_report.webp` | `burr` | 잔여 버 검사 요약·세부 표 |
| `crop_monitor.webp` | `runlive` | 실시간 공정 패널 |
| `wide_blindspot.webp` | `blind` | Blind Spot 판정 원리·결과 |
| `wide_market.webp` | `cagr` | 두 시장의 연평균 성장률 |

**값은 크롭 화면에 찍혀 있던 값 그대로다.** 새로 지어낸 수치는 없다.
파형(`runlive`)과 감쇠 곡선(`rlpolicy`)만 형태 예시이고 그 사실을 캡션에 적었다.

### 서브셋에 없는 글리프를 쓰지 마라

`✓`(U+2713) · `○`(U+25CB) · `π` · `Ø` · `−`(U+2212) 는 Pretendard 서브셋 928자에
**없다.** 판정 표시는 글리프 대신 `.gr::before` 로 점을 그리고 옆에 글자를 붙였다
(색만으로 알리지 않는다는 규칙과도 맞는다). 음수는 en dash `–` 를 쓴다.

```bash
# 서브셋에 그 글자가 있는지 먼저 확인해라
python -c "from fontTools.ttLib import TTFont; f=TTFont('assets/fonts/Pretendard-500.subset.woff2'); \
  print(any(0x2713 in t.cmap for t in f['cmap'].tables))"
```

### 나머지 4장 — 잘라내기와 라벨 지우기

그림 자체는 살려야 하는데 글자만 한글인 경우다. 원본은
`assets/img/_precrop_2026-08-31/` (배포 제외).

| 그림 | 한 일 | 크기 |
|---|---|---|
| `crop_ansys.webp` | 위아래 한글 띠를 잘라냈다. 안쪽 ANSYS 캡처는 원래 영어다 | 1200×900 → **1076×586** |
| `crop_force.webp` | 제목·범례·설명 띠를 잘라내고 그래프만 남겼다. 축 숫자는 언어 중립. 제목과 범례는 `force` 도해가 마크업으로 올린다 | 1200×906 → **1140×467** |
| `crop_collision.webp` | 구워져 있던 「충돌 위험」을 지우고 `ovFig` 로 얹었다 | 그대로 |
| `crop_preston.webp` | 「연마 패드」·「연마 대상」 동일 | 그대로 |

지우는 방법은 **라벨 사각형 위·아래 한 줄을 세로로 선형 보간**해 채우는 것이다.
주변을 평균낸 단색으로 덮으면 매끈한 배경에 사각형 자국이 남는다.
라벨 위치는 원본 픽셀에서 실측한 퍼센트다 — 눈대중으로 넣지 마라.

### 남은 6장은 손대지 않았다

`wide_system` · `wide_loop` · `wide_path` · `wide_result` · `wide_rl_overview` ·
`pdf_20_*.jpg` 는 실제 인물 사진, Isaac Sim 캡처, 히트맵이 한 장에 합성된
슬라이드다. 다시 생성하면 **다른 그림**이 나오지 원본이 복원되지 않고,
숫자는 기획서 실측값이라 모델이 지어내면 `수치는 기획서에 있는 값만 쓴다` 가
깨진다. 캡션만 마크업이므로 번역은 캡션까지만 된다.

`ASSET_V` 를 `2026-08-31h` 로 올렸다. 검수는 17개 서브 페이지 전부 —
깨진 그림 0, 콘솔 오류 0, 390px 폭에서 가로 스크롤 없음.

---

## 그림 안의 한글 → 영문판 (2026-09-01)

랜딩(`index.html`)은 `<img>` 가 0개다. 도해가 전부 인라인 SVG라
`assets/js/i18n.js` 의 사전이 글자를 그대로 잡아 EN 에서 영어로 바뀐다.
`sub.html` 은 래스터 `.webp` 를 쓰고 글자가 픽셀에 구워져 있어 안 바뀌었다.

### 손댈 것은 18장 중 6장뿐이었다

| | |
|---|---|
| 한글이 박힘 | `wide_loop` `wide_system` `wide_rl_overview` `wide_result` `wide_path` `pdf_20_*` |
| 언어 중립 | `crop_scan` `crop_path` `crop_boundary` `crop_blindspot` `crop_deburr_run` `crop_sand_grit` `crop_sand_quality` `crop_pose` `crop_collision` `crop_preston` `wide_docs` |
| 원래 영문 | `crop_ansys` (ANSYS 캡처) |

위 「남은 6장은 손대지 않았다」를 대체한다. **다시 생성하지 않았다** —
원본을 복사해 한글 자리만 덮고 그 자리에 Pretendard 로 영문을 그렸다.
차체 와이어프레임·로봇·레이더 차트·히트맵·인물 사진은 원본 픽셀 그대로다.
숫자(`20.0` `1,800 rpm` `85.6` `04:12`)와 원래 영문(`ANSYS` `ROS 2` `Isaac Sim`
`Expert Evaluation` `J1–J6`)은 건드리지 않았다.

```bash
python scripts/i18n-figures.py            # 6장 전부
python scripts/i18n-figures.py wide_loop  # 한 장
python scripts/i18n-figures.py wide_loop --debug   # 지울 자리를 빨간 상자로
python scripts/i18n-figures.py wide_loop --audit   # 상자가 글자를 다 덮는지
```

좌표·문구는 `scripts/figspec.py` 에 있다. 원본 6장은
`assets/img/_prei18n_2026-08-31/` 에 보관하고 배포에서 제외한다.

### 지우는 방법 — 사각형이 아니라 글자 마스크

라벨 하나를 지우던 앞 절의 세로 보간은 여기서 안 통한다. 상자를 가로지르는
레이더 차트 선·카드 테두리가 세로로 번져 얼룩이 된다. 그래서

1. 상자 안에서 **밝기 임계를 넘는 픽셀만** 글자로 보고 마스크를 만든다
   (흰 말풍선 안 검은 글씨는 `th` 를 음수로 줘 반대로 잡는다),
2. 안티에일리어싱 가장자리까지 먹도록 `grow` 만큼 부풀리고 **상자 안으로 다시 자른다**
   (안 자르면 드롭다운 화살표 같은 옆 그림을 먹는다),
3. 그 픽셀만 **같은 줄의 좌우 배경을 선형 보간**해 채운다.

사방으로 확산시키면 상자 밖(드롭다운 밖 패널 배경 같은)의 다른 색이 끌려
들어와 어두운 얼룩이 생긴다. 좌우 기증 픽셀의 밝기가 크게 다르면 한쪽이
글자·아이콘 가장자리라는 뜻이므로 배경 쪽(어두운 UI면 어두운 쪽)을 쓴다.

`--audit` 은 상자 안 획에서 이어지는 픽셀이 상자를 넘는지 보고한다.
`오비탈 · 스파이럴 · 리니어` 가 상자보다 7px 왼쪽에서 시작하던 것을 이걸로 찾았다.
번호 원(①②③)·체크표시·색 칩처럼 **남겨야 하는 그림**도 같이 걸리므로
경고 목록은 눈으로 한 번 본다.

### Pretendard 서브셋에는 ASCII 밖 문자가 없다

`assets/fonts/Pretendard-*.full-ko.woff2` 는 한글 + ASCII 서브셋이다.
가운뎃점(`·`)·따옴표(`’`)·화살표(`→`)·`×`·`°` 가 전부 빠져 있어 그리면 두부(□)가 된다.
브라우저는 대체 글꼴로 넘기지만 PIL 은 안 넘긴다. `i18n-figures.py` 의 `check()`
가 그리기 전에 막는다 — `·` 는 `/`, `→` 는 `->`, `×` 는 `x`, `°` 는 `deg` 로 쓴다.

### 붙이는 쪽

`i18n.js` 의 `IMG_EN` 이 `lang=en` 일 때 `<img src>` 만 갈아 끼운다
(`?v=` 캐시 버스터는 유지). KR 로 돌아가면 원본으로 복귀한다.
`<main data-i18n="off">` 안에서도 교체한다 — 본문 번역이 안 끝난 것과
그림 글자가 한국어인 것은 별개다. 이미 `.en` 인 그림은 `IMG_EN` 에 없어
다시 걸리지 않으므로 MutationObserver 가 여러 번 돌아도 안전하다.

| | 원본 | 영문판 |
|---|---|---|
| `wide_loop` | 124 KB | 126 KB |
| `wide_path` | 130 KB | 129 KB |
| `wide_result` | 91 KB | 96 KB |
| `wide_rl_overview` | 109 KB | 112 KB |
| `wide_system` | 150 KB | 164 KB |
| `pdf_20_*` | 172 KB | 241 KB (JPEG q82 · 4:4:4 — 글자가 뭉개지지 않게) |
| **합계** | **776 KB** | **868 KB** |

영문판은 EN 에서만 받는다. KR 사용자의 첫 로드에는 안 들어간다.

### 본문 글자 — `assets/js/i18n-sub.js`

그림과 별개로 `sub.html` 본문(17개 서브 페이지)도 옮겼다.
`<main>` 에 걸려 있던 `data-i18n="off"` 를 뗐고, 본문 사전 764개를
`i18n-sub.js` 로 나눴다 — 98 KB(gzip 36 KB)라 랜딩 첫 로드에 얹을 수 없다.
`sub.html` 만 `i18n.js` 앞에 이 파일을 싣고, `i18n.js` 가 있으면 합친다.

키는 화면의 한국어 원문 그대로다. 본문이 `<b>813</b>개` 처럼 인라인 요소로
끊겨 있어 텍스트 노드 단위로 토막 키가 많다 — 숫자를 사이에 두고도 말이
되도록 영문을 골랐다(`스캔 1회 →` + 813 + `waypoints generated`).

```bash
python scripts/i18n-check.py          # 사전에 없는 본문 문장 (없어야 정상)
python scripts/i18n-check.py --keys   # 본문에서 사라진 사전 키
```

**본문에 문장을 추가하면 이 검사를 돌려라.** 사전에 없으면 EN 화면의 그
문단만 한국어로 남는다. 한 문단 안에 두 언어가 섞이는 게 제일 나쁘다.

`document.title` 도 손봤다. `sub.html` 은 페이지를 바꿀 때마다 제목을 다시
쓰는데 `i18n.js` 가 로드 시점 값을 붙들고 있어서, EN 에서 탭 제목이 첫
페이지 이름으로 되돌아갔다. 이제 스냅숏 대신 그때그때 현재 제목을 읽는다
(`transTitle` · `syncTitle`).

### 값과 이어 붙는 노드 (2026-09-01)

`sub.html` 의 벤치마크 표에서 한 줄만 한국어로 남아 있었다.

```html
<p class="gen__o"><b>${v}</b> — ${note}</p>
```

런타임에 이것은 텍스트 노드 **하나**다 — 「— 합성 숙련공 기준…」. 사전에는
「합성 숙련공 기준…」 만 있어서 맞지 않았다. `i18n-check.py` 가 이걸 놓친 이유는
값을 뽑을 때 `${...}` 를 지우고 봤기 때문이다. 지우고 나면 사전에 있는 형태와
같아 보인다.

고친 방법은 구분선을 떼어 노드를 나눈 것이다. `<span>` 은 색도 굵기도
물려받으므로 화면은 그대로다.

```html
<p class="gen__o"><b>${v}</b> <span class="sep">—</span> ${note}</p>
```

세 곳이었다 — `gens` · `market` · `bench`. 같은 유형을 다시 놓치지 않도록
`i18n-check.py` 에 `--glue` 를 붙였다(기본 실행에도 들어간다). 태그 경계 안에서
정적 글자와 `${}` 가 한 노드로 붙는 자리를 찾는다. 중첩 템플릿
(`${B.map(([k, v]) => \`…\`)}`) 안까지 재귀로 들어간다 — 처음에는 거기서
빠뜨렸다.

## 앱 화면 영문화 — ① 콘솔 · ② 모니터 · ④ 라이브러리 (2026-09-01)

랜딩과 `sub.html` 은 번역됐는데 헤더가 직접 링크하는 앱 화면 세 개는
`i18n.js` 자체를 싣지 않았다. EN 에서 「① 사전 설정」 을 누르면 전면 한국어
UI 로 떨어지고, 그 화면에는 언어 전환 버튼도 없어 되돌아올 수도 없었다.

### 세 화면은 생김새가 다르다

| 화면 | 파일 | 형태 |
|---|---|---|
| ② 모니터 | `monitor.html` | 평범한 HTML — 끝에 `<script>` 두 줄 |
| ① 콘솔 | `PolyTwin Console.html` | 번들러 아티팩트 (599 KB) |
| ④ 라이브러리 | `PolyTwin Library.html` | 번들러 아티팩트 (166 KB) |

번들 두 개는 실제 문서가 `<script type="__bundler/template">` 안에 **JSON
문자열 한 덩이**로 들어 있고, 로더가 그걸 파싱해
`document.documentElement.replaceWith()` 로 통째로 갈아 끼운다.

**그래서 바깥 껍데기에 `<script>` 를 달면 안 된다.** 갈아 끼우는 순간
i18n 이 붙잡고 있던 `body` 가 문서에서 떨어져 나간다. 템플릿 **안**에 넣어야
로더의 스크립트 재생성 루프가 새 문서에서 다시 실행한다.

```bash
python scripts/i18n-bundle-patch.py          # 심는다 (두 번 돌려도 안전)
python scripts/i18n-bundle-patch.py --check  # 심겼는지 본다
```

**번들을 다시 구우면 이 패치가 날아간다.** 그때 다시 돌려라.

### 사전 두 벌 — `assets/js/i18n-app.js`

앱 화면의 글은 값과 함께 자바스크립트에서 이어 붙는다.

```js
'도달 ' + assigned + ' / ' + points + ' pt · 미도달 구간은 검증 리포트로 남는다'
```

숫자가 매번 달라지므로 노드 전체를 키로 둘 수 없다. 그래서 두 벌을 쓴다.

- `PT_DICT_APP` — 노드 하나가 통째로 맞을 때. **기본 수단이다.**
- `PT_PHRASES_APP` — 노드 안의 한 토막만. 위가 안 될 때만.

토막은 **긴 것부터** 맞춘다. 짧은 토막이 긴 문장 안을 파고들면 반쪽짜리
영어가 되는데, 그건 한국어로 남는 것보다 나쁘다. 한 글자짜리(`행`·`대`)는
`진행`·`대비` 같은 낱말 속에 있으므로 숫자 뒤에 붙은 것만 바꾸도록
정규식으로 뒀다.

```bash
python scripts/i18n-app-check.py            # 사전에 없는 화면 글 (없어야 정상)
python scripts/i18n-app-check.py --anchors  # 언어 전환 상자가 붙을 자리
python scripts/i18n-app-check.py --phrases  # 다른 문장 속을 파고드는 토막
```

번들은 이 검사기가 템플릿을 꺼내 읽는다 — 원본은 건드리지 않는다.

### 언어 전환 상자

세 화면의 헤더가 제각각이고 번들은 마크업을 직접 고치기 어렵다. 그래서
`i18n-app.js` 가 화면이 그려진 뒤에 끼워 넣는다. 붙는 자리는 순서대로
`.bar`(②) → `main nav`(④) → `main > header`(①). `class="lang"` 을 달아
`i18n.js` 의 기존 클릭 처리와 `paintSwitch` 를 그대로 쓴다.

### 옵서버 간격

②는 매 프레임 수치를 다시 쓴다. 그때마다 `MutationObserver` 가 깨어 문서
전체를 훑으면 3D 뷰와 프레임을 다툰다. 화면 글이 60번/초로 바뀔 일은 없으므로
최소 간격 120 ms 를 뒀다(`i18n.js` 의 `GAP`). 첫 번째는 미루지 않는다.

### 남은 것

`PolyTwin Save.html`(③)과 `admin.html` 은 한국어 그대로다. ②·④에서 「③ 결과
저장」 을 누르면 EN 에서도 한국어 화면이 나온다. 옮기려면 같은 방법이다 —
`i18n-app.js` 에 사전을 더하고 `i18n-bundle-patch.py` 의 `FILES` 에 넣으면 된다.

`index.html` 의 3D 로더 실패 문구 두 개(`모델을 불러오지 못했다 —`,
`file:// 로는 fetch가 막힌다…`)도 한국어다. 로컬에서 서버 없이 열었을 때만
뜨는 경로라 그대로 뒀다.

### 배포 증가분

| | 크기 | gzip |
|---|---|---|
| `i18n-app.js` | 18.6 KB | 7.5 KB |
| 번들 두 개 | +196 B 씩 | — |

`i18n-app.js` 는 앱 화면에서만 받는다. 랜딩 첫 로드에는 안 들어간다.

---

## 제조사 마크 — ① 차종 선택 (2026-09-01)

차종 카드 위에 있던 회색 알약(`swatch`, `#6E7681` 계열 리터럴 4개)은 아무
정보도 주지 않았다. 제조사 마크로 바꿨다.

### 넣을 파일

`frontend/assets/icons/` 에 아래 이름으로 둔다. 경로는 `console-src/template.html`
의 `CARS[].mark` 에 박혀 있다.

| 파일 | 차종 | 원본 |
|---|---|---|
| `bmw.png` | BMW Z4 | `_orig/bmw.png` |
| `benz.png` | 벤츠 쿠페 | `_orig/Benz.jpg` |
| `ferrari.png` | 페라리 SF90 | `_orig/ferrari.png` |
| `hyundai.png` | 현대 쏘나타 | `_orig/hyundai.png` |

원본은 흰 바탕에 원색이라 그대로 못 얹는다. Benz 는 JPG 라 알파가 아예
없고, 현대는 남색이라 배경에 묻히고, 페라리는 노란 방패가 패널에서 제일
밝은 덩어리가 되고, 현대에는 「HYUNDAI」 워드마크까지 붙어 있었다.

### 누끼 · 톤 정규화

`python scripts/logo-mono.py` 로 재현한다. `_orig/` 를 읽어 같은 이름으로
덮어쓴다.

1. **흰 배경 → 알파.** 채도가 있으면 잉크, 무채색은 밝기로 부드럽게 깎아
   가장자리를 살린다. BMW 흰 사분면처럼 로고 *안쪽* 흰색도 같이 뚫린다 —
   어두운 배경에서는 그게 맞다. BMW 공식 다크 로고가 그 모양이다.
2. **회색조.** 원색을 그대로 두면 이 패널에만 색 체계가 넷 더 생기고
   DESIGN.md 「액센트 1개」 원칙이 깨진다.
3. **잉크 평균 밝기를 0.55 로 감마 보정.** 잉크가 어두운 페라리·현대는
   먼저 반전한다. 페라리는 반전하면 방패 바닥이 배경으로 가라앉고
   윤곽·말·SF 만 남아 26px 에서 더 잘 읽힌다.
4. **광학 크기 균형.** 바운딩박스가 아니라 눈에 보이는 덩어리로 맞춘다.
   넓은 타원(현대 0.90)은 같은 폭이면 커 보이고, 세로형(페라리 1.06)은
   작아 보인다.

결과는 LA(회색조+알파) PNG 128px, 넷 합쳐 **35 KB**.

```css
.veh-mark { width: 26px; height: 26px; object-fit: contain; }
```

**CSS 에서 `filter` 를 걸지 마라.** 톤은 파일에 구워져 있다 — 또 걸면
두 번 밝아진다. 선택 상태만 불투명도로 준다 (0.45 → 1).

마스크(`mask-image`)로 단색 실루엣을 만드는 방법은 쓰지 않았다. BMW
사분면·페라리 말처럼 안쪽이 분할된 마크는 알파만 남아 통짜 덩어리가 된다.

`_orig/` 는 `.vercelignore` 로 배포에서 뺀다.

### 파일이 없을 때

`alt=""` 라 브라우저가 깨진 이미지 아이콘을 그리지 않는다. 빈칸으로
떨어지고 아래 차종 이름은 그대로 보인다.
