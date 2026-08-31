# [Fable 세션용 프롬프트] PolyTwin — Vercel 풀스택 배포

아래를 새 세션에 그대로 붙여넣는다.

---

PolyTwin 웹 콘솔을 **Vercel에 풀스택으로 배포**해라. 작업 디렉터리는
`C:\Users\ShinHyeonHo\Desktop\해커톤 UI\polytwin_UI` 이고, 이 폴더가 배포 루트다
(상위 폴더가 아니다 — 상위에는 배포하면 안 되는 자료가 700MB 있다).

## 0. 먼저 읽어라 (순서대로)

1. `CLAUDE.md` — 디자인·성능 규칙. **UI는 건드리지 마라. 이번 작업은 배포다.**
2. `SERVER.md` — 현재 로컬 서버의 동작 계약
3. `server/server.js` (459줄) · `server/db.js` (132줄) · `server/auth.js` (40줄) — 포팅 대상 전부
4. `ASSETS.md` — 자산이 왜 이 구조인지 (base64 인라인 금지의 이유)

## 1. 현재 구조 (실측 — 다시 조사할 필요 없다)

- **프론트엔드**: 순수 정적 HTML 5장 + 자산
  - 공개: `index.html`
  - 로그인 필요: `sub.html`(15개 슬러그) · `monitor.html` · `PolyTwin Console.html` · `PolyTwin Library.html` (파일명에 공백 있음 — URL 인코딩으로 접근된다)
  - 관리자 전용: `admin.html`
- **백엔드**: `server/server.js` — 의존성 0개 Node 서버
  - API 8종: `POST /api/signup` · `POST /api/login` · `POST /api/logout` · `GET /api/me` · `GET /api/admin/users` · `GET /api/admin/audit` · `PATCH·DELETE /api/admin/users/:id`
  - DB: `node:sqlite` (Node 22.5+ 내장), 테이블 3개 — `users` / `sessions` / `audit`. 파일은 `data/polytwin.db`
  - 인증: scrypt 해시(`server/auth.js`) + 랜덤 세션 토큰, 쿠키 `pt_sid` (HttpOnly·SameSite=Lax·12시간)
  - 접근 제어: `.html` 요청만 게이팅. `PUBLIC_PAGES = {/, /index.html}` 외의 HTML은 세션 없으면 `302 /?login=1&next=…`, `admin.html`은 role=admin 아니면 403. **자산(/assets, .js, .css)은 열려 있다**
  - 로그인 레이트리밋: 인메모리 Map (IP+ID 기준)
  - 최초 기동 시 admin 계정 시드: `PT_ADMIN_ID`(기본 admin) / `PT_ADMIN_PW`(기본 polytwin2026)

## 2. 목표 아키텍처 — 이렇게 가라

Vercel 서버리스에서는 두 가지가 **그대로는 안 된다**. 이게 이번 작업의 본질이다:

1. **SQLite 파일이 유지되지 않는다** — 함수 파일시스템은 읽기 전용(/tmp 제외)이고 인스턴스 간 공유도 안 된다.
2. **인메모리 상태(레이트리밋 Map)가 인스턴스마다 따로 논다.**

### 결정 사항 (재논의 말고 이대로)

- **DB: Turso (libSQL)** — 스키마가 SQLite 그대로 옮겨져서 `server/db.js`의 SQL을 거의 안 바꾼다. 의존성은 `@libsql/client` 하나만 추가한다. (이 프로젝트는 의존성 0개 철학이지만, 서버리스에서 영속 DB는 불가피하다 — 이 한 개 외에는 아무것도 설치하지 마라. express·bcrypt 금지.)
- **API: 캐치올 함수 하나** — `api/[[...route]].js` 에 server.js의 API 분기를 포팅한다. 라우팅 프레임워크 없이 지금처럼 pathname 분기면 충분하다. scrypt는 `node:crypto` 그대로 쓴다 (Node 런타임 함수로 — Edge 아님).
- **HTML 게이팅: `middleware.js` (Edge Middleware)** — 정적 HTML은 CDN이 서빙하므로 302 게이팅은 미들웨어에서 한다. Edge에서 DB 조회는 하지 마라. 대신:
  - 세션 쿠키를 **HMAC 서명 토큰**으로 바꾼다: `base64url(payload).base64url(HMAC-SHA256(payload, PT_SECRET))`, payload = `{uid, role, exp}`. Edge에서 `crypto.subtle`로 서명만 검증 → 통과/302/403 판정. (role은 admin.html 판정에 필요하다)
  - DB의 `sessions` 테이블은 유지한다 — 로그아웃·강제 만료(revocation)는 API 라우트(`/api/me` 등)에서 DB 대조로 잡는다. Edge는 서명+만료만 본다. 이 절충을 코드 주석에 적어라.
  - 게이팅 대상·공개 목록·리다이렉트 형식(`/?login=1&next=…`)은 지금과 동일하게. **동작 계약을 바꾸지 마라.**
- **레이트리밋**: 인스턴스-로컬 Map 그대로 유지하되 "서버리스에서는 best-effort"라는 주석을 남겨라. Upstash 추가하지 마라 — 데모 규모에 과하다.
- **로컬 개발 경로 보존**: `node server/server.js` 는 계속 그대로 돌아야 한다. DB 접근을 `server/db.js` 인터페이스 뒤에 두고, 로컬=node:sqlite / Vercel=libsql 로 갈라라 (env `TURSO_DATABASE_URL` 유무로 분기). 공통 로직(라우트 핸들러·auth)은 한 벌만 두고 양쪽에서 임포트해라 — 복붙 두 벌 금지.

### 환경 변수 (Vercel 대시보드)

| 변수 | 용도 |
|---|---|
| `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` | DB 연결 |
| `PT_SECRET` | 세션 토큰 HMAC 키 (32바이트 랜덤) |
| `PT_ADMIN_ID` / `PT_ADMIN_PW` | admin 시드. **프로덕션에서 PT_ADMIN_PW 미설정이면 시드를 거부하고 에러 로그를 남겨라** — 기본값 polytwin2026을 공개 서버에 두면 안 된다 |

admin 시드는 "최초 기동"이라는 개념이 서버리스에 없으므로, 별도 시드 스크립트(`scripts/seed-admin.mjs`, 로컬에서 Turso로 실행)로 옮겨라.

## 3. 배포 대상 정리 (.vercelignore / .gitignore)

디렉터리 전체는 708MB다. 다음을 반드시 제외해라:

- `*.backup-*.html` · `*.html.bak` · `_snapshot_*/ ` · `_probe.html`
- `assets/models/_orig/` · `assets/img/_orig_light/`
- `assets/new_img/` — **단, 제외 전에 HTML 5장에서 참조 여부를 grep으로 확인**하고, 참조가 있으면 그 파일만 남겨라
- `data/*.db*` (DB 파일을 절대 커밋·배포하지 마라)
- `console-src/` · `polytwin_sourcecode/` · `데이터셋/sweep_traj_csv*` (사이트가 fetch하는 `데이터셋/*.json` 은 **포함**해야 한다 — Console·Library가 읽는다)
- 검수 도구(`asset-check.html` `rig-check.html` `clip-check.html`)는 배포에서 제외

제외 후 배포 크기가 **약 50–60MB**(영상 30MB 포함)면 정상이다. 100MB를 넘으면 뭘 잘못 포함한 것이다.

git 저장소가 아니다 — `polytwin_UI` 에서 `git init` 하고 위 ignore를 먼저 커밋한 뒤 진행해라.

## 4. 함정 목록 (알고 시작해라)

- `PolyTwin Console.html` 등 **파일명 공백** — 사이트 내 링크가 `href="PolyTwin Console.html"` 형태다. Vercel 정적 서빙에서 인코딩된 요청이 잘 매핑되는지 배포 후 반드시 확인해라.
- `.glb` MIME — `model/gltf-binary` 로 나가는지 확인 (vercel.json headers로 지정 가능).
- 영상은 range 요청이 되는지 확인 (Vercel CDN은 지원한다 — 확인만).
- `데이터셋/` 폴더명이 한글이다 — fetch 경로 인코딩 확인.
- 서버가 지금 자산에 `max-age=3600` 을 준다 — vercel.json에서 `/assets/*` 는 `public, max-age=31536000, immutable` 로 올리되, **HTML은 no-cache**로 둬라 (HTML 5장이 자주 바뀐다).
- HTTPS이므로 세션 쿠키에 `Secure` 플래그를 추가해라 (로컬 http에서는 빼고).

## 5. 검증 — 이걸 통과해야 완료다

로컬 (`vercel dev`)과 배포 프리뷰 **양쪽에서** curl로:

1. `GET /` → 200
2. `GET /sub.html?p=safety` (비로그인) → **302, Location: /?login=1&next=%2Fsub.html**
3. `POST /api/login` (`{"loginId":…,"password":…}`) → 200 + Set-Cookie
4. 쿠키 포함 `GET /sub.html?p=safety` → 200
5. 일반 계정 쿠키로 `GET /admin.html` → 403, admin 쿠키로 → 200
6. `POST /api/logout` 후 같은 쿠키로 sub.html → 302 (revocation 동작 확인)
7. `GET /assets/models/car.opt.glb` → 200 + 올바른 Content-Type
8. `GET /PolyTwin%20Console.html` (로그인 쿠키) → 200
9. 회원가입 → pending 상태 → admin 승인 → 로그인 흐름 1회 왕복

가능하면 헤드리스 크롬으로 배포 URL 스크린샷을 찍어 3D 뷰포트와 폰트가 뜨는지 눈으로 확인해라.

## 6. 사용자에게 물어봐야 하는 것 (멈추고 확인)

- Vercel 로그인/팀 선택 (`vercel login` · `vercel link`)
- Turso 계정 생성과 DB 프로비저닝 (직접 못 하면 명령을 사용자에게 안내)
- 프로덕션 admin 비밀번호 (절대 네가 정하지 마라)
- 커스텀 도메인 여부

## 7. 산출물

- `api/[[...route]].js` · `middleware.js` · `vercel.json` · `.vercelignore` · `.gitignore` · `scripts/seed-admin.mjs`
- `server/db.js` 이원화 (로컬 sqlite / Turso) — 로컬 `node server/server.js` 회귀 없음 확인 포함
- `SERVER.md` 에 "Vercel 배포" 섹션 추가 (env 표, 시드 절차, 검증 curl 목록)
- 배포 프리뷰 URL + 위 검증 9개 항목의 실제 결과 보고 (실패 항목은 실패로 보고해라 — 되는 척 금지)

**하지 마라**: UI/디자인 수정, 새 색상, 새 프레임워크 도입(Next.js로 재작성 금지 — 정적 HTML 그대로 간다), 자산 base64 인라인, `@libsql/client` 외의 의존성 추가, DB 파일 커밋, 기본 비밀번호로 프로덕션 배포.
