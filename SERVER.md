# PolyTwin 계정 서버

**작성** 2026-08-29 · 의존성 **0개**. `npm install` 없이 돈다.

`node:sqlite`(Node 22.5+ 내장)와 `node:crypto`만 쓴다. bcrypt·express·better-sqlite3
어느 것도 받지 않는다 — 이 프로젝트는 자산 용량 때문에 한 번 크게 데였고,
같은 실수를 `node_modules`로 반복하지 않는다.

---

## 실행

```bash
node backend/server.js      # 또는 npm start
# → http://127.0.0.1:8000
```

**`python -m http.server`는 더 이상 쓰지 않는다.** 로그인·계정 API가
정적 서버에는 없다. 3D 자산 검수(`appendix/tools/asset-check.html`)도 이 서버로 열면 된다.

### 최초 기동

관리자 계정이 없으면 하나 만들고 콘솔에 찍는다.

```
ID        admin
PASSWORD  polytwin2026
```

**데모용 기본값이다.** 바꾸려면 둘 중 하나:

```bash
PT_ADMIN_PW='원하는-비밀번호' node backend/server.js   # 최초 1회에만 반영
```
또는 로그인 후 `/admin.html` → 해당 계정 **비번 초기화**.

### 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8000` | 포트 |
| `HOST` | `127.0.0.1` | 바인딩 주소. 같은 망에서 보려면 `0.0.0.0` |
| `PT_DB` | `backend/data/polytwin.db` | DB 경로 |
| `PT_SIM_MODE` | `local` (Vercel 에선 `queue`) | `local`: 실행 버튼이 이 PC 의 Isaac 을 직접 띄움. `queue`: 작업 행만 만들고 GPU 워커가 가져감 |
| `PT_SIM_REPO` | `../cacadaca` | (local) 시뮬 저장소 경로 |
| `PT_MONITOR_FEED` | `<PT_SIM_REPO>/learning/ui_bridge/out/monitor_feed.json` | (local) 시뮬이 쓰는 실시간 피드 파일 |
| `PT_WORKER_TOKEN` | 없음 | (queue) 워커 인증 토큰 — 없으면 워커 API 가 모두 403 |

### WAL 주의

로컬 DB 는 WAL 모드다(읽기·쓰기가 서로를 막지 않게). 그래서 **서버가 도는
동안 `polytwin.db` 파일만 열면 내용이 안 보인다** — 최근 쓴 것이 전부
`polytwin.db-wal` 에 있고, `.db` 만 읽는 뷰어(VS Code Database Client 등)는
'No tables available' 을 띄운다. 파일이 4KB 근처면 그 상태다.

`Ctrl+C` 로 정상 종료하면 `backend/server.js` 가 `store.checkpoint()` 를
불러 WAL 을 본 파일로 접고 나간다. 강제 종료(kill -9)했다면 직접 접어라:

```bash
node -e "require('./backend/db.js').checkpoint()"
```
| `PT_ADMIN_ID` | `admin` | 씨앗 관리자 ID (최초 1회) |
| `PT_ADMIN_PW` | `polytwin2026` | 씨앗 관리자 비밀번호 (최초 1회) |

---

## 접근 제어

**화면 보호는 서버가 한다.** 클라이언트 가드는 개발자도구로 지워지므로 보호가 아니다.
`.html` 요청은 **기본 차단(deny-by-default)** 이고, 아래만 예외다.

| 경로 | 누구에게 |
|---|---|
| `/`, `/index.html` | 누구나 (랜딩) |
| `/assets/**`, 영상·모델 등 자산 | 누구나 |
| 그 밖의 모든 `.html` | 로그인한 계정 |
| `/admin.html`, `/api/admin/**` | `role = admin` 만 |

로그인 없이 보호된 화면을 요청하면 `/?login=1&next=<경로>` 로 302 된다.
랜딩이 그 신호를 받아 로그인 창을 열고, 성공하면 원래 가려던 화면으로 보낸다.

새 화면을 추가하면 **기본이 차단**이다. 공개해야 하면
`backend/server.js` 의 `PUBLIC_PAGES` 에 넣어라.

---

## 계정

| 필드 | 값 |
|---|---|
| `role` | `admin` · `engineer` |
| `status` | `pending` · `active` · `suspended` |

- 회원가입은 항상 **`pending`** 으로 들어온다. 관리자가 승인해야 접속된다.
- `active` 가 아닌 계정은 로그인 자체가 막힌다.
- 상태를 `active` 밖으로 바꾸거나 비밀번호를 바꾸면 **그 계정의 세션을 즉시 끊는다.**
- **활성 관리자가 한 명뿐이면** 강등·정지·삭제가 거부된다. 자기 계정도 삭제 불가.
  스스로를 잠그고 DB를 지워야 하는 상황을 만들지 않는다.

### 비밀번호

`scrypt` (N=16384, r=8, p=1, 64바이트) + 계정마다 다른 16바이트 솔트.
저장 형식은 `scrypt$N$r$p$salt$hash`. 비교는 `timingSafeEqual`.

### 세션

`pt_sid` 쿠키 — `HttpOnly`, `SameSite=Lax`, 12시간. 토큰은 32바이트 난수.
DB의 `sessions` 표에 있고 만료분은 한 시간마다 쓸어낸다.

> `Secure` 플래그는 붙이지 않았다. localhost는 http라 붙이면 쿠키가 안 실린다.
> **https로 배포한다면 반드시 켜라** — `backend/server.js` 의 `Set-Cookie` 두 곳.

---

## API

| 메서드 | 경로 | 권한 | 하는 일 |
|---|---|---|---|
| `POST` | `/api/signup` | 누구나 | 가입 신청 (`pending` 생성) |
| `POST` | `/api/login` | 누구나 | 로그인, 쿠키 발급 |
| `POST` | `/api/logout` | 누구나 | 세션 파기 |
| `GET` | `/api/me` | 누구나 | 현재 로그인 상태 |
| `GET` | `/api/library` | 로그인 | 합격 기록 목록 (전원 공유, 최근 200건) |
| `POST` | `/api/library` | 로그인 | 합격 기록 저장 (`ref_id` 중복이면 기존 것 반환) |
| `DELETE` | `/api/library/:id` | 본인·admin | 합격 기록 삭제 |
| `GET` | `/api/dataset/seg-best-kpi` | 로그인 | 숙련공 정답 데이터 (세그먼트 15) |
| `GET` | `/api/dataset/quality-kpi` | 로그인 | 품질 기준 · 에피소드 |
| `GET` | `/api/admin/users` | admin | 계정 목록 |
| `GET` | `/api/admin/audit` | admin | 최근 기록 60건 |
| `PATCH` | `/api/admin/users/:id` | admin | `status` · `role` · `password` |
| `DELETE` | `/api/admin/users/:id` | admin | 삭제 |

`pw_hash`는 어떤 응답에도 나가지 않는다 (`publicUser()` 한 곳에서만 직렬화).

### 막아 둔 것

- **계정 열거** — ID가 없든 비번이 틀리든 같은 401 문구.
- **무차별 대입** — IP+ID 기준 5분에 10회. 넘으면 429.
- **경로 탈출** — 해석된 경로가 프로젝트 루트 밖이면 403.
- **뒤로가기 노출** — `.html` 은 `Cache-Control: no-store`.

---

## 파일

```
backend/server.js       정적 파일(../frontend) + 라우팅 + 접근 제어
backend/routes.js       API — 로컬·Vercel 공용
backend/db.js           스키마와 질의 (node:sqlite / Turso)
                        테이블 6: users · sessions · audit
                                  library_entries (합격 기록)
                                  segments · dataset_meta (숙련공 정답 데이터)
backend/auth.js         scrypt 해시 · 세션 토큰
backend/middleware.js   Edge 게이팅 본체
backend/data/polytwin.db  DB. 지우면 다음 기동에 관리자만 다시 생긴다
admin.html         계정 관리 화면 (admin 전용)
assets/js/auth-client.js   헤더 세션 표시 · 로그아웃 · API 래퍼
```

---

## 아직 안 한 것

- **비밀번호 찾기** — 랜딩 로그인 창의 링크는 아직 창만 닫는다. 메일 발송 경로가 없다.
- **CSRF 토큰** — `SameSite=Lax` + JSON 본문 요구로 대부분 막히지만 토큰은 없다.
  외부에 열 거면 붙여야 한다.
- **HTTPS** — 위 `Secure` 플래그 항목 참고.
- **Console·Library·Save 화면의 로그아웃 버튼** — 번들 파일이라 건드리지 않았다.
  서버가 접근은 막지만 그 화면 안에서 로그아웃할 수는 없다.

---

## Vercel 배포 (2026-08-31 추가)

정적 HTML 은 CDN, `/api/*` 는 서버리스 함수, HTML 게이팅은 Edge Middleware.
로컬 `node backend/server.js` 는 그대로 돈다 — 같은 라우트 코드(`backend/routes.js`)를 쓴다.

| 파일 | 역할 |
|---|---|
|  `api/index.js` | `/api/*` 단일 함수 — rewrite 가 원 경로를 `__path` 로 전달 · `backend/routes.js` 위임 |
| `middleware.js` (루트) | `backend/middleware.js` 재수출 샴 — Vercel 이 루트에서만 찾는다 |
| `backend/middleware.js` | HTML 302/403 게이팅 (HMAC 서명 쿠키 검증, DB 안 봄) |
| `backend/db.js` | `TURSO_DATABASE_URL` 있으면 Turso(libSQL), 없으면 로컬 node:sqlite |
| `vercel.json` | `outputDirectory: frontend` · 자산 캐시(immutable) · HTML no-store · .glb MIME |
| `scripts/seed-admin.mjs` | 관리자 계정 시드 (`npm run seed`) |
| `scripts/seed-datasets.mjs` | 숙련공 정답 데이터 시드 (`npm run seed:data`) |

### 환경 변수 (Vercel 프로젝트 설정)

| 변수 | 값 |
|---|---|
| `TURSO_DATABASE_URL` | `libsql://<db>-<org>.turso.io` |
| `TURSO_AUTH_TOKEN` | Turso 토큰 |
| `PT_SECRET` | 32바이트 랜덤 (`node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"`) |
| `PT_WORKER_TOKEN` | GPU PC 워커와 공유하는 랜덤 토큰 (같은 방법으로 생성) |

### 절차

```bash
# 1. Turso DB 만들기 (계정: turso.tech)
turso db create polytwin && turso db show polytwin --url && turso db tokens create polytwin

# 2. 관리자 시드 — 기본 비밀번호로는 거부된다
TURSO_DATABASE_URL=… TURSO_AUTH_TOKEN=… PT_ADMIN_PW='강한-비밀번호' npm run seed

# 2-1. 숙련공 정답 데이터 시드 — 안 하면 ①·④ 화면이 503 을 받는다
TURSO_DATABASE_URL=… TURSO_AUTH_TOKEN=… npm run seed:data

# 3. 배포
vercel login && vercel link && vercel --prod
```

### 시뮬레이션 워커 (GPU PC)

Vercel 에는 GPU·Isaac 이 없으므로 콘솔의 실행 버튼은 작업(`sim_jobs`)만 만든다. 시뮬 저장소의
워커가 이 서버를 폴링해 작업을 가져가 Isaac 을 돌리고, 실시간 피드(`sim_state.feed`, 1 KB 덮어쓰기)와
결과 요약(`sim_jobs.result`)을 올린다. 아웃바운드 HTTPS 만 쓰므로 GPU PC 가 NAT 뒤에 있어도 된다.

```bash
# GPU PC (시뮬 저장소 cacadaca 루트에서) — PT_WORKER_TOKEN 은 Vercel 과 같은 값
python3 learning/ui_bridge/sim_worker.py --server https://<app>.vercel.app --token <PT_WORKER_TOKEN>
python3 learning/ui_bridge/sim_worker.py --server http://127.0.0.1:8000 --token <t> --fake --once   # 연결 확인(합성 피드)
```

워커 API(헤더 `X-PT-Worker: <토큰>`): `GET /api/sim/jobs/next?worker=<이름>` 클레임 →
`POST /api/sim/jobs/:id/feed` {feed} (응답 `stopRequested`) → `POST …/result` {result} → `POST …/exit` {exitCode,status}.
브라우저 쪽은 모드와 무관하게 `POST /api/sim/start|stop`, `GET /api/sim/status`, `GET /api/monitor` 를 쓴다.

### 시뮬 기록(리플레이)

워커는 작업마다 시뮬 프레임(관절각·베이스·힘·상태·진행·공정시간)을 SQLite 로 기록하고 2 s 마다 청크를 올린다:
`POST /api/sim/runs` {job_id, name, meta} → `POST /api/sim/runs/:id/chunks` {chunks:[{seq,t0,t1,n,data(base64 gzip JSON)}]},
`…/events`, `…/cells`, `…/meta`, `…/finish` {status, result}. 브라우저(세션)는 `GET /api/runs`, `GET /api/runs/:id`,
`GET /api/runs/:id/chunks?from=<s>&to=<s>`, `…/events`, `…/cells?after=` 로 받아 보간 재생한다(콘솔 "기록 재생").
로컬에서만 `POST /api/runs/import {path}` 로 기록 sqlite 파일을 서버 DB 에 복사할 수 있다.
용량: 10 Hz·로봇 3대 ≈ 1.2 KB/s (18 h ≈ 80 MB) — Turso 무료 한도(5 GB) 안이지만 오래된 런은 지울 것.
DB 에는 작업 파라미터·최신 피드 한 줄·결과 요약만 들어가고 타일 데이터셋·힘 로그 같은 큰 파일은 GPU PC 에 남는다.

### 세션 구조 (왜 이렇게인가)

토큰 = `v1.<payload>.<HMAC-SHA256>` — Edge 는 서명·만료만 보고 HTML 을 게이팅하고
(DB 호출 없음), `/api/*` 는 DB 의 sessions 행까지 대조한다(로그아웃·강제 만료).
강제 만료된 토큰이 만료 시각까지 HTML 게이트를 통과할 수 있는 절충은
HTML 에 데이터가 없으므로 수용 — 데이터는 전부 API 뒤에 있다.

주의: 서버리스에서 로그인 레이트리밋은 인스턴스-로컬 best-effort 다.
