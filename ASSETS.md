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
| **`.subset`** | 300/500/700 | 실제 쓰는 825자 | **171 KB** | −99.0% |
| `.full-ko` | 300/500/700 | 한글 11,172자 전체 | 1.75 MB | −89.2% |

### 어느 것을 쓸까

- **`.full-ko`를 권한다.** 1.75 MB면 예산 안이고, **앞으로 어떤 한글을 써도 깨지지 않는다.**
- `.subset`(171 KB)은 현재 텍스트에 등장한 632자만 들어 있다. 카피를 한 글자라도
  바꾸면 그 글자가 두부(□)로 나온다. **데모 직전에 문구를 안 바꾼다고 확신할 때만.**

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
    Pretendard-{300,500,700}.subset.woff2    171 KB   ← 문구 고정 시
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
