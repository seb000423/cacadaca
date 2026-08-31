# PolyTwin

자동차 차체를 로봇팔이 자동 폴리싱하는 공정의 **관제·설정 웹 콘솔**.
파라미터를 정하고 → 공정을 지켜보고 → 잘 나온 설정을 저장하고 → 나중에 다시 꺼내 쓴다.

사용자는 공정 엔지니어다. 랜딩(⓪)만 인상을 만드는 화면이고, 나머지는 작업 화면이다.

---

## 화면

| 파일 | 화면 | 하는 일 |
|---|---|---|
| `index.html` | ⓪ 랜딩 | 브랜드·제품 소개. 로그인 창이 여기 붙어 있다 |
| `sub.html?p=<id>` | 서브 문서 | 공정별(폴리싱·디버링·샌딩·Pick&Place)·기술별(Physical AI·강화학습·숙련공 DB·안전 검증) 상세와 News/Media/Blog/FAQ |
| `PolyTwin Console.html` | ① 사전 설정 | 파라미터 슬라이더 + 3D 미리보기 |
| `monitor.html` | ② 공정 모니터링 | 실시간 차트, 커버리지, 카메라 뷰 |
| `PolyTwin Library.html` | ③④ 라이브러리 | 결과 지표·히트맵, 숙련공 데이터 저장·불러오기·비교 |
| `PolyTwin Save.html` | 저장 | 설정 스냅샷 |
| `admin.html` | 계정 관리 | `role = admin` 전용 |

`sub.html` 의 `p` 값: `values` `results` `pricing` `polishing` `deburring` `sanding`
`pickplace` `roadmap` `physical-ai` `rl` `expert-db` `safety` `news` `media` `blog` `faq`

---

## 실행

```bash
npm run seed:data           # 최초 1회 — 숙련공 정답 데이터를 DB 에 넣는다
node backend/server.js      # 또는 npm start
# → http://127.0.0.1:8000
```

의존성은 로컬 기준 0개다. `node:sqlite`(Node 22.5+ 내장)와 `node:crypto`만 쓴다.
`npm install` 은 Vercel 배포용 `@libsql/client` 때문에만 필요하다.

**`python -m http.server` 로는 안 된다.** 로그인·계정 API가 정적 서버에는 없다.

`seed:data` 를 건너뛰면 ①·④ 화면이 정답 데이터를 못 받아 503 을 띄운다.
원본은 `frontend/데이터셋/*.json` 이고, 이 명령이 `segments` · `dataset_meta` 테이블로 옮긴다.

최초 기동 시 관리자 계정이 없으면 하나 만들고 콘솔에 찍는다 (`admin` / `polytwin2026`).
데모용 기본값이므로 배포 전에 바꿔라. 자세한 내용은 [SERVER.md](SERVER.md).

### 접근 제어

`.html` 요청은 **기본 차단**이다. `/`, `/index.html`, `/assets/**` 만 공개고
나머지는 로그인, `/admin.html` 은 admin 만 통과한다.
새 화면을 공개하려면 `backend/server.js` 의 `PUBLIC_PAGES` 에 넣어야 한다.

---

## 배포

Vercel — 정적 HTML 은 CDN, `/api/*` 는 서버리스 함수 하나(`api/index.js`),
HTML 게이팅은 Edge Middleware(`middleware.js`), DB 는 Turso(libSQL).
함수 리전은 서울(`icn1`) 고정이다.

필요한 환경 변수는 `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `PT_SECRET`.
절차와 세션 구조는 [SERVER.md](SERVER.md) 의 배포 절에 있다.

---

## 디렉터리

```
api/index.js         /api/* 단일 서버리스 함수
middleware.js        루트 샴 → backend/middleware.js (Vercel 요구)
backend/             routes.js · db.js · auth.js · server.js · middleware.js · data/
frontend/            배포 루트 (vercel.json outputDirectory)
frontend/console-src/  ① 화면 편집 원본 + repack.py
frontend/library-src/  ③④ 화면 편집 원본 + repack.py
frontend/save-src/     저장 화면 편집 원본 + repack.py
appendix/            예전 버전 · 원본 소스 · 검수 도구 · 끝난 문서
scripts/             폰트 서브셋 · 이미지 보정 · 검수 · 관리자 시드
frontend/assets/models/  meshopt 압축 모델 (_orig/ 는 비교용, 배포 제외)
frontend/assets/fonts/   Pretendard 서브셋
frontend/assets/vendor/  three.js r169 + 애드온 + MeshoptDecoder
frontend/데이터셋/       sweep 궤적 CSV, KPI JSON, 생성 스크립트
```

### 번들 화면을 고치는 법

`PolyTwin Console.html` · `Library.html` · `Save.html` 은 번들러 결과물이라
직접 편집하지 않는다. 대응하는 `*-src/` 의 `template.html`(과 콘솔은 `viewport.js`)을
고치고 되돌려 넣는다.

```bash
python frontend/console-src/repack.py
```

---

## 3D

```js
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.outputColorSpace = THREE.SRGBColorSpace;
scene.environment = pmrem.fromScene(envScene, 0.03).texture;
new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);   // .opt.glb 는 이게 없으면 안 열린다
```

모델마다 스케일이 3자릿수 넘게 차이난다(샌딩킷 0.003 단위, 차체 27 단위).
카메라는 고정 좌표가 아니라 **바운딩 스피어 기준 자동 프레이밍**이어야 한다.

검수는 로컬 서버를 띄우고 `appendix/tools/asset-check.html` 로 한다 — 압축 모델을 원본과 나란히 놓고 본다.
리그·클립 검수는 `rig-check.html`, `clip-check.html`.

---

## 자산 현황

| 항목 | 예산 | 현재 |
|---|---|---|
| 3D 모델 합계 (`*.opt.glb`) | < 3 MB | 3.3 MB |
| 폰트 (서브셋 3종) | < 2 MB | 0.19 MB |
| LCP | < 2.5 s | — |

**자산을 base64로 HTML에 박지 마라.** 그것 때문에 파일이 한 번 89 MB가 됐다.
감축 기록과 재현 방법은 [ASSETS.md](ASSETS.md).

---

## 문서

| 파일 | 내용 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 작업 규칙. 하지 않을 것 / 반드시 할 것 |
| [DESIGN.md](DESIGN.md) | 색·타이포·간격·모션 토큰 (코드에서 감사해 확정한 값) |
| [ASSETS.md](ASSETS.md) | 모델·폰트 감축 기록과 재현 절차 |
| [SERVER.md](SERVER.md) | 계정 서버, 접근 제어, API, 배포 |
| [UI목업_프롬프트_폴리트윈_2026-08-25.md](appendix/docs/UI목업_프롬프트_폴리트윈_2026-08-25.md) | 원래 기획 의도와 화면별 요구사항 |
| [AI티제거_지침서_폴리트윈_2026-08-27.md](appendix/docs/AI티제거_지침서_폴리트윈_2026-08-27.md) | 디자인 판단의 배경 |
