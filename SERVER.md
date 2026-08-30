# PolyTwin 계정 서버

**작성** 2026-08-29 · 의존성 **0개**. `npm install` 없이 돈다.

`node:sqlite`(Node 22.5+ 내장)와 `node:crypto`만 쓴다. bcrypt·express·better-sqlite3
어느 것도 받지 않는다 — 이 프로젝트는 자산 용량 때문에 한 번 크게 데였고,
같은 실수를 `node_modules`로 반복하지 않는다.

---

## 실행

```bash
node server/server.js      # 또는 npm start
# → http://127.0.0.1:8000
```

**`python -m http.server`는 더 이상 쓰지 않는다.** 로그인·계정 API가
정적 서버에는 없다. 3D 자산 검수(`asset-check.html`)도 이 서버로 열면 된다.

### 최초 기동

관리자 계정이 없으면 하나 만들고 콘솔에 찍는다.

```
ID        admin
PASSWORD  polytwin2026
```

**데모용 기본값이다.** 바꾸려면 둘 중 하나:

```bash
PT_ADMIN_PW='원하는-비밀번호' node server/server.js   # 최초 1회에만 반영
```
또는 로그인 후 `/admin.html` → 해당 계정 **비번 초기화**.

### 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8000` | 포트 |
| `HOST` | `127.0.0.1` | 바인딩 주소. 같은 망에서 보려면 `0.0.0.0` |
| `PT_DB` | `data/polytwin.db` | DB 경로 |
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
`server/server.js` 의 `PUBLIC_PAGES` 에 넣어라.

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
> **https로 배포한다면 반드시 켜라** — `server/server.js` 의 `Set-Cookie` 두 곳.

---

## API

| 메서드 | 경로 | 권한 | 하는 일 |
|---|---|---|---|
| `POST` | `/api/signup` | 누구나 | 가입 신청 (`pending` 생성) |
| `POST` | `/api/login` | 누구나 | 로그인, 쿠키 발급 |
| `POST` | `/api/logout` | 누구나 | 세션 파기 |
| `GET` | `/api/me` | 누구나 | 현재 로그인 상태 |
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
server/server.js   정적 파일 + 라우팅 + 접근 제어
server/db.js       스키마와 질의 (node:sqlite)
server/auth.js     scrypt 해시 · 세션 토큰
data/polytwin.db   DB. 지우면 다음 기동에 관리자만 다시 생긴다
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
로컬 `node server/server.js` 는 그대로 돈다 — 같은 라우트 코드(`server/routes.js`)를 쓴다.

| 파일 | 역할 |
|---|---|
| `api/[[...route]].js` | `/api/*` 캐치올 — `server/routes.js` 위임 |
| `middleware.js` | HTML 302/403 게이팅 (HMAC 서명 쿠키 검증, DB 안 봄) |
| `server/db.js` | `TURSO_DATABASE_URL` 있으면 Turso(libSQL), 없으면 로컬 node:sqlite |
| `vercel.json` | 자산 캐시(immutable) · HTML no-store · .glb MIME |
| `scripts/seed-admin.mjs` | 원격 DB 관리자 시드 (`npm run seed`) |

### 환경 변수 (Vercel 프로젝트 설정)

| 변수 | 값 |
|---|---|
| `TURSO_DATABASE_URL` | `libsql://<db>-<org>.turso.io` |
| `TURSO_AUTH_TOKEN` | Turso 토큰 |
| `PT_SECRET` | 32바이트 랜덤 (`node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"`) |

### 절차

```bash
# 1. Turso DB 만들기 (계정: turso.tech)
turso db create polytwin && turso db show polytwin --url && turso db tokens create polytwin

# 2. 관리자 시드 — 기본 비밀번호로는 거부된다
TURSO_DATABASE_URL=… TURSO_AUTH_TOKEN=… PT_ADMIN_PW='강한-비밀번호' npm run seed

# 3. 배포
vercel login && vercel link && vercel --prod
```

### 세션 구조 (왜 이렇게인가)

토큰 = `v1.<payload>.<HMAC-SHA256>` — Edge 는 서명·만료만 보고 HTML 을 게이팅하고
(DB 호출 없음), `/api/*` 는 DB 의 sessions 행까지 대조한다(로그아웃·강제 만료).
강제 만료된 토큰이 만료 시각까지 HTML 게이트를 통과할 수 있는 절충은
HTML 에 데이터가 없으므로 수용 — 데이터는 전부 API 뒤에 있다.

주의: 서버리스에서 로그인 레이트리밋은 인스턴스-로컬 best-effort 다.
