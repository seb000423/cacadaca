/* ══════════════════════════════════════════════════════════════
   PolyTwin API 라우트 — 로컬 서버와 Vercel 함수가 공유하는 한 벌

   backend/server.js (로컬) →  handleApi(req, res, pathname)
   api/[[...route]].js      →  동일 호출

   두 환경 모두 Node req/res 다. 여기 없는 것: 정적 파일 서빙
   (로컬은 server.js, Vercel 은 CDN+middleware.js 가 맡는다).
   ══════════════════════════════════════════════════════════════ */
'use strict';

const store = require('./db');
const { verifyPassword, signSession, parseSession } = require('./auth');

const SESSION_TTL = 1000 * 60 * 60 * 12;   /* 12시간 */
const COOKIE = 'pt_sid';

/* ── 유틸 ─────────────────────────────────────────────────── */
function json(res, code, body) {
  const buf = Buffer.from(JSON.stringify(body));
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': buf.length,
    'Cache-Control': 'no-store',
  });
  res.end(buf);
}

function parseCookies(header) {
  const out = {};
  String(header || '').split(';').forEach((part) => {
    const i = part.indexOf('=');
    if (i < 0) return;
    out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  });
  return out;
}

function readBody(req, limit) {
  /* Vercel Node 런타임은 JSON 본문을 미리 파싱해 req.body 에 둔다.
     그때 스트림을 다시 읽으면 영영 안 끝난다 — 있으면 그걸 쓴다 */
  if (req.body !== undefined) {
    if (typeof req.body === 'object' && req.body !== null) return Promise.resolve(req.body);
    if (typeof req.body === 'string') {
      try { return Promise.resolve(req.body ? JSON.parse(req.body) : {}); }
      catch { return Promise.reject(new Error('invalid json')); }
    }
  }
  const cap = limit || 64 * 1024;
  return new Promise((resolve, reject) => {
    const chunks = [];
    let n = 0;
    req.on('data', (c) => {
      n += c.length;
      if (n > cap) { reject(new Error('payload too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (!raw) { resolve({}); return; }
      try { resolve(JSON.parse(raw)); } catch { reject(new Error('invalid json')); }
    });
    req.on('error', reject);
  });
}

/* 화면에 내보내는 사용자 형태. pw_hash 는 절대 나가지 않는다 */
function publicUser(u) {
  if (!u) return null;
  return {
    id: u.id,
    loginId: u.login_id,
    name: u.name,
    role: u.role,
    status: u.status,
    createdAt: u.created_at,
    lastLoginAt: u.last_login_at,
  };
}

/* 저장 행 → 클라이언트 형태. payload 를 펴서 예전 localStorage
   레코드와 같은 모양으로 돌려준다 — 라이브러리 렌더 코드를 그대로 쓴다 */
function publicEntry(row) {
  let body = {};
  try { body = JSON.parse(row.payload); } catch { body = {}; }
  const at = new Date(Number(row.created_at));
  const pad = (n) => String(n).padStart(2, '0');
  return {
    id: String(row.ref_id),
    rowId: Number(row.id),
    seg: row.seg || '',
    name: row.name || '',
    date: pad(at.getMonth() + 1) + '-' + pad(at.getDate()) + ' ' + pad(at.getHours()) + ':' + pad(at.getMinutes()),
    savedAt: Number(row.created_at),
    owner: row.owner_name || row.owner_login || '',
    env: body.env || null,
    rl: body.rl || null,
    ref: body.ref || null,
  };
}

/* 프록시(Vercel) 뒤에서는 소켓 주소가 프록시다 — 헤더 우선 */
const clientIp = (req) =>
  String(req.headers['x-forwarded-for'] || '').split(',')[0].trim()
  || (req.socket && req.socket.remoteAddress) || '?';

const isHttps = (req) =>
  req.headers['x-forwarded-proto'] === 'https' || (req.socket && req.socket.encrypted);

function sessionCookie(req, token, maxAgeSec) {
  return COOKIE + '=' + token + '; Path=/; HttpOnly; SameSite=Lax; Max-Age=' + maxAgeSec
    + (isHttps(req) ? '; Secure' : '');
}

/** 쿠키 → 서명 검증 → DB 대조. 강제 만료(revocation)는 여기서 잡힌다 */
async function sessionOf(req) {
  const token = parseCookies(req.headers.cookie)[COOKIE];
  if (!parseSession(token)) return null;      /* 서명·만료 — 위조는 DB 도 안 간다 */
  return store.readSession(token);            /* 로그아웃·강제 만료 대조 */
}

/* ── 로그인 시도 제한 ── 무차별 대입을 늦춘다.
   서버리스에서는 인스턴스마다 따로 노는 best-effort 다 — 콜드 스타트가
   카운터를 비우지만, scrypt 비용 + 계정 열거 차단이 본 방어선이다 ── */
const attempts = new Map();
const RL = { max: 10, windowMs: 5 * 60 * 1000 };

function rateLimited(key) {
  const t = Date.now();
  const rec = attempts.get(key);
  if (!rec || rec.resetAt < t) { attempts.set(key, { n: 1, resetAt: t + RL.windowMs }); return false; }
  rec.n += 1;
  return rec.n > RL.max;
}

/* ── 검증 ─────────────────────────────────────────────────── */
const ID_RE = /^[A-Za-z0-9._-]{4,32}$/;

function validateSignup(loginId, password, name) {
  if (!loginId || !ID_RE.test(loginId)) return 'ID는 영문·숫자·. _ - 조합 4~32자여야 합니다.';
  if (!password || password.length < 8) return '비밀번호는 8자 이상이어야 합니다.';
  if (password.length > 200) return '비밀번호가 너무 깁니다.';
  if (name && String(name).length > 40) return '이름이 너무 깁니다.';
  return '';
}

/* ══════════════════════════════════════════════════════════════
   API
   ══════════════════════════════════════════════════════════════ */
/* ── 시뮬레이션 실행 모드 ─────────────────────────────────
   local : 이 서버가 Isaac 을 직접 띄운다 (UI 서버와 GPU 가 같은 PC)
   queue : 작업 큐에 넣고 GPU PC 의 워커(sim_worker.py)가 가져간다 (Vercel 배포 기본)
   PT_SIM_MODE 로 강제, 없으면 Vercel 이면 queue, 아니면 local. ── */
function simMode() {
  const m = String(process.env.PT_SIM_MODE || '').toLowerCase();
  if (m === 'local' || m === 'queue') return m;
  return process.env.VERCEL ? 'queue' : 'local';
}
function workerAuthed(req) {
  const want = process.env.PT_WORKER_TOKEN || '';
  if (!want) return false;
  const got = String(req.headers['x-pt-worker'] || '');
  return got.length === want.length && require('crypto').timingSafeEqual(Buffer.from(got), Buffer.from(want));
}
function jobPublic(j) {
  if (!j) return null;
  let params = null, result = null;
  try { params = JSON.parse(j.params); } catch { params = null; }
  try { result = j.result ? JSON.parse(j.result) : null; } catch { result = null; }
  return { id: j.id, status: j.status, stopRequested: !!j.stop_requested, params, worker: j.worker,
           createdAt: j.created_at, startedAt: j.started_at, finishedAt: j.finished_at, exitCode: j.exit_code, result };
}

async function handleApi(req, res, pathname) {
  const method = req.method;

  /* ── 가입 ── 기본 상태는 pending. 관리자 승인 전에는 못 들어온다 ── */
  if (pathname === '/api/signup' && method === 'POST') {
    const body = await readBody(req);
    const loginId = String(body.loginId || '').trim();
    const name = String(body.name || '').trim();
    const password = String(body.password || '');

    const bad = validateSignup(loginId, password, name);
    if (bad) return json(res, 400, { error: bad });
    if (await store.findByLogin(loginId)) return json(res, 409, { error: '이미 사용 중인 ID입니다.' });

    const u = await store.createUser({ loginId, name, password, role: 'engineer', status: 'pending' });
    await store.log(loginId, 'signup', loginId, 'from ' + clientIp(req));
    return json(res, 201, {
      user: publicUser(u),
      message: '가입 신청이 접수되었습니다. 관리자 승인 후 접속할 수 있습니다.',
    });
  }

  /* ── 로그인 ── */
  if (pathname === '/api/login' && method === 'POST') {
    const body = await readBody(req);
    const loginId = String(body.loginId || '').trim();
    const password = String(body.password || '');
    const key = clientIp(req) + '|' + loginId.toLowerCase();

    if (rateLimited(key)) {
      await store.log(loginId || '?', 'login.throttled', loginId, clientIp(req));
      return json(res, 429, { error: '시도가 너무 많습니다. 5분 후 다시 시도하세요.' });
    }
    if (!loginId || !password) return json(res, 400, { error: 'ID와 비밀번호를 입력하세요.' });

    const u = await store.findByLogin(loginId);
    /* ID 유무를 알려주지 않는다 — 계정 열거를 막는다 */
    if (!u || !verifyPassword(password, u.pw_hash)) {
      await store.log(loginId, 'login.fail', loginId, clientIp(req));
      return json(res, 401, { error: 'ID 또는 비밀번호가 올바르지 않습니다.' });
    }
    if (u.status === 'pending') return json(res, 403, { error: '관리자 승인 대기 중인 계정입니다.' });
    if (u.status === 'suspended') return json(res, 403, { error: '정지된 계정입니다. 관리자에게 문의하세요.' });

    attempts.delete(key);
    /* 토큰 = HMAC 서명 (Edge 게이팅용) + DB 행 (revocation 용). 형식은 auth.js 참고 */
    const token = signSession({ uid: u.id, role: u.role, exp: Date.now() + SESSION_TTL });
    await store.createSession(u.id, token, SESSION_TTL);
    await store.touchLogin(u.id);
    await store.log(u.login_id, 'login', u.login_id, clientIp(req));
    /* 만료 세션 청소 — 서버리스에는 기동 시점이 없어 여기서 겸한다 */
    store.sweepSessions().catch(() => {});

    res.setHeader('Set-Cookie', sessionCookie(req, token, SESSION_TTL / 1000));
    return json(res, 200, { user: publicUser(await store.findById(u.id)) });
  }

  /* ── 로그아웃 ── */
  if (pathname === '/api/logout' && method === 'POST') {
    const token = parseCookies(req.headers.cookie)[COOKIE];
    const sess = await store.readSession(token);
    if (token) await store.dropSession(token);
    if (sess) await store.log(sess.login_id, 'logout', sess.login_id, '');
    res.setHeader('Set-Cookie', sessionCookie(req, '', 0));
    return json(res, 200, { ok: true });
  }

  /* ── 현재 사용자 ── */
  if (pathname === '/api/me' && method === 'GET') {
    const sess = await sessionOf(req);
    return json(res, 200, { user: sess ? publicUser(sess) : null });
  }

  /* ══ 숙련공 정답 데이터 ═══════════════════════════════════
     예전에는 화면이 데이터셋/*.json 을 직접 fetch 했다. 이제 DB 다.
     돌려주는 모양은 그 JSON 과 똑같이 맞춘다 — 화면 쪽은 URL 만
     바뀌고 파싱 코드는 그대로 쓴다.
     원본 CSV(183MB)는 DB 에 넣지 않는다. 세그먼트가 들고 있는
     byteStart/byteEnd 로 여전히 정적 파일에 Range 요청을 건다. ══ */
  /* ══ 시뮬레이션 실시간 피드 (② 모니터) ═══════════════════════
     Isaac Sim 쪽(learning/ui_bridge/monitor_feed.py)이 JSON 파일을 20 스텝마다 갱신하고
     여기서는 그 파일을 읽어 돌려준다. 파일이 없거나 5 s 이상 오래되면 live:false —
     monitor.html 은 그때 데모 데이터로 돌아간다. 경로는 PT_MONITOR_FEED 로 바꾼다. ══ */
  /* ══ 시뮬레이션 런처 (① 콘솔 → Isaac Sim) ═══════════════════════
     콘솔의 실행/정지 버튼이 실제 폴리싱 시뮬(원코드 v5 + 잔차 정책)을 띄우고 내린다.
     로컬 서버 전용 — Vercel 함수에서는 프로세스를 띄울 수 없어 501 을 돌려준다.
       POST /api/sim/start {tool, force, rpm, feed_mm_s, overlap, robotCount, physical, max_steps, dry_run}
       POST /api/sim/stop
       GET  /api/sim/status → {running, pid, startedAt, elapsed_s, params, exitCode, result}
     경로: PT_SIM_REPO(시뮬 저장소, 기본 ../cacadaca), PT_ISAAC_PY(기본 ~/isaacsim/python.sh) ══ */
  /* ── 워커 전용 (X-PT-Worker 토큰) — 큐 모드의 GPU PC 가 부른다 ── */
  /* ── 워커 → 시뮬 기록 업로드 (리플레이/지연 재생용) ── */
  if (pathname.indexOf('/api/sim/runs') === 0) {
    if (!workerAuthed(req)) return json(res, 401, { error: '워커 토큰이 필요합니다.' });
    const mm = pathname.match(/^\/api\/sim\/runs(?:\/(\d+)(?:\/(chunks|events|cells|finish|meta))?)?$/);
    if (!mm) return json(res, 404, { error: 'not found' });
    const b64 = (v) => Buffer.from(String(v || ''), 'base64');
    if (!mm[1] && method === 'POST') {
      const body = await readBody(req);
      const id = await store.createRun({ jobId: body.job_id != null ? Number(body.job_id) : null, name: String(body.name || ''), meta: body.meta || {} });
      return json(res, 200, { ok: true, run_id: id });
    }
    const run = mm[1] ? await store.getRun(Number(mm[1])) : null;
    if (!run) return json(res, 404, { error: 'run not found' });
    if (mm[2] === 'chunks' && method === 'POST') {
      const body = await readBody(req, 8 * 1024 * 1024);
      const chunks = (body.chunks || []).map((c) => ({ seq: Number(c.seq), t0: Number(c.t0), t1: Number(c.t1), n: Number(c.n), data: b64(c.data) }));
      await store.appendChunks(run.id, chunks);
      return json(res, 200, { ok: true, last_seq: await store.lastChunkSeq(run.id) });
    }
    if (mm[2] === 'events' && method === 'POST') {
      const body = await readBody(req);
      await store.addRunEvents(run.id, body.events || []);
      return json(res, 200, { ok: true });
    }
    if (mm[2] === 'cells' && method === 'POST') {
      const body = await readBody(req, 8 * 1024 * 1024);
      await store.addRunCells(run.id, (body.cells || []).map((c) => ({ id: Number(c.id), t: Number(c.t), data: b64(c.data) })));
      return json(res, 200, { ok: true });
    }
    if (mm[2] === 'meta' && method === 'POST') {
      const body = await readBody(req);
      await store.updateRunMeta(run.id, body.meta || {});
      return json(res, 200, { ok: true });
    }
    if (mm[2] === 'finish' && method === 'POST') {
      const body = await readBody(req);
      await store.finishRun(run.id, body.status === 'failed' ? 'failed' : 'done', body.result || null);
      return json(res, 200, { ok: true });
    }
    if (!mm[2] && method === 'GET') return json(res, 200, { ok: true, run: { ...run, last_seq: await store.lastChunkSeq(run.id) } });
    return json(res, 405, { error: 'method' });
  }

  if (pathname.indexOf('/api/sim/jobs') === 0) {
    if (!workerAuthed(req)) return json(res, 401, { error: '워커 토큰이 필요합니다.' });
    if (pathname === '/api/sim/jobs/next' && method === 'GET') {
      const u = new URL(req.url, 'http://localhost');
      const worker = String(u.searchParams.get('worker') || 'gpu');
      const j = await store.claimNextJob(worker);
      return json(res, 200, { job: jobPublic(j) });
    }
    const m = pathname.match(/^\/api\/sim\/jobs\/(\d+)\/(feed|result|exit|state)$/);
    if (m) {
      const id = Number(m[1]); const kind = m[2];
      const j = await store.getJob(id);
      if (!j) return json(res, 404, { error: '없는 작업입니다.' });
      if (kind === 'state' && method === 'GET') return json(res, 200, { job: jobPublic(j) });
      if (method !== 'POST') return json(res, 405, { error: '지원하지 않는 요청입니다.' });
      const body = await readBody(req, 512 * 1024);
      if (kind === 'feed') { await store.putState('feed', body.feed || body); return json(res, 200, { ok: true, stopRequested: !!j.stop_requested }); }
      if (kind === 'result') { await store.setJobResult(id, body.result || body); return json(res, 200, { ok: true }); }
      if (kind === 'exit') {
        const code = Number(body.exitCode);
        const status = body.status || (j.stop_requested ? 'stopped' : (code === 0 ? 'done' : 'failed'));
        const jj = await store.finishJob(id, { status, exitCode: Number.isFinite(code) ? code : -1, result: body.result || null });
        return json(res, 200, { ok: true, job: jobPublic(jj) });
      }
    }
    return json(res, 404, { error: '없는 요청입니다.' });
  }
  if (pathname.indexOf('/api/sim/') === 0 && simMode() === 'queue') {
    /* ── 큐 모드: 콘솔 → 작업 행, 워커가 실행 ── */
    const sess = await sessionOf(req);
    if (!sess) return json(res, 401, { error: '로그인이 필요합니다.' });
    if (sess.status !== 'active') return json(res, 403, { error: '승인 대기 중인 계정입니다.' });
    if (pathname === '/api/sim/status' && method === 'GET') {
      const active = await store.activeJob();
      const j = active || await store.latestJob();
      const jp = jobPublic(j);
      return json(res, 200, {
        mode: 'queue', running: !!(active), queued: !!(active && active.status === 'queued'),
        pid: null, startedAt: jp ? jp.startedAt : null, params: jp ? jp.params : null,
        exitCode: jp ? jp.exitCode : null, log: null, job: jp,
        elapsed_s: jp && jp.startedAt ? Math.round((Date.now() - jp.startedAt) / 1000) : 0,
        result: jp && (jp.status === 'done' || jp.status === 'stopped' || jp.status === 'failed') ? jp.result : null,
      });
    }
    if (pathname === '/api/sim/stop' && method === 'POST') {
      const active = await store.activeJob();
      if (!active) return json(res, 200, { ok: true, running: false });
      await store.requestStop(active.id);
      await store.log(sess.login_id, 'sim.stop', String(active.id), 'queue');
      return json(res, 200, { ok: true, running: true, stopping: true, job: jobPublic(await store.getJob(active.id)) });
    }
    if (pathname === '/api/sim/start' && method === 'POST') {
      const active = await store.activeJob();
      if (active) return json(res, 409, { error: '이미 대기/실행 중인 작업이 있습니다.', job: jobPublic(active) });
      const body = await readBody(req, 64 * 1024);
      const num = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d);
      const params = {
        tool: String(body.tool || 'dual'), force: num(body.force, 5.6), rpm: num(body.rpm, 3000),
        feed_mm_s: num(body.feed_mm_s, 5.65), overlap: num(body.overlap, 40),
        robotCount: num(body.robotCount, 3), physical: !!body.physical, max_steps: num(body.max_steps, 6000),
        hasRail: body.hasRail === undefined ? true : !!body.hasRail, hasLift: body.hasLift === undefined ? true : !!body.hasLift,
        pad: num(body.pad, 110), carLift: num(body.carLift, 0),
      };
      if (params.force < 3 || params.force > 8) return json(res, 400, { error: '접촉력은 3~8 N 대역 안이어야 합니다.' });
      if (body.dry_run) return json(res, 200, { ok: true, dry_run: true, mode: 'queue', params });
      const j = await store.createJob({ userId: Number(sess.id), params });
      await store.log(sess.login_id, 'sim.start', String(j.id), JSON.stringify(params));
      return json(res, 201, { ok: true, mode: 'queue', job: jobPublic(j) });
    }
    return json(res, 404, { error: '없는 요청입니다.' });
  }
  if (pathname.indexOf('/api/sim/') === 0) {
    const sess = await sessionOf(req);
    if (!sess) return json(res, 401, { error: '로그인이 필요합니다.' });
    if (process.env.VERCEL) return json(res, 501, { error: '배포 서버에서는 시뮬레이션을 실행할 수 없습니다.' });
    const fs = require('fs'), path = require('path'), os = require('os');
    const { spawn } = require('child_process');
    const REPO = process.env.PT_SIM_REPO || path.join(__dirname, '..', '..', 'cacadaca');
    const ISAAC = process.env.PT_ISAAC_PY || path.join(os.homedir(), 'isaacsim', 'python.sh');
    const OUT = path.join(REPO, 'learning', 'ui_bridge', 'out');
    const feed = process.env.PT_MONITOR_FEED || path.join(OUT, 'monitor_feed.json');
    global.__ptSim = global.__ptSim || { proc: null, pid: null, startedAt: null, params: null, exitCode: null, log: null };
    const S = global.__ptSim;
    const running = !!(S.proc && S.exitCode === null);
    if (pathname === '/api/sim/status' && method === 'GET') {
      let result = null;
      try {
        const rp = path.join(OUT, 'last_run.json');
        const st = fs.statSync(rp);
        if (!S.startedAt || st.mtimeMs >= S.startedAt - 1000) result = JSON.parse(fs.readFileSync(rp, 'utf8'));
      } catch (e) { result = null; }
      return json(res, 200, {
        running, pid: S.pid, startedAt: S.startedAt, params: S.params, exitCode: S.exitCode, log: S.log,
        elapsed_s: S.startedAt ? Math.round((Date.now() - S.startedAt) / 1000) : 0, result,
      });
    }
    if (pathname === '/api/sim/stop' && method === 'POST') {
      if (!running) return json(res, 200, { ok: true, running: false });
      try { process.kill(-S.proc.pid, 'SIGTERM'); } catch (e) { try { S.proc.kill('SIGTERM'); } catch (e2) { /* ignore */ } }
      await store.log(sess.login_id, 'sim.stop', String(S.pid), '');
      return json(res, 200, { ok: true, running: true, stopping: true });
    }
    if (pathname === '/api/sim/start' && method === 'POST') {
      if (running) return json(res, 409, { error: '이미 실행 중입니다.', pid: S.pid });
      const body = await readBody(req, 64 * 1024);
      const num = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d);
      const params = {
        tool: String(body.tool || 'dual'), force: num(body.force, 5.6), rpm: num(body.rpm, 3000),
        feed_mm_s: num(body.feed_mm_s, 5.65), overlap: num(body.overlap, 40),
        robotCount: num(body.robotCount, 3), physical: !!body.physical, max_steps: num(body.max_steps, 6000),
        hasRail: body.hasRail === undefined ? true : !!body.hasRail, hasLift: body.hasLift === undefined ? true : !!body.hasLift,
        pad: num(body.pad, 110), carLift: num(body.carLift, 0),
      };
      if (params.force < 3 || params.force > 8) return json(res, 400, { error: '접촉력은 3~8 N 대역 안이어야 합니다.' });
      /* 레시피 JSON — 시뮬 저장소의 윗면 레시피를 바탕으로 콘솔 값을 덮어쓴다.
         경로 간격 = 패드 지름 × (1 − 오버랩) → step_over_spacing_ratio */
      let recipe = {};
      try { recipe = JSON.parse(fs.readFileSync(path.join(REPO, 'learning', 'polytwin', 'outputs', 'bo_best_recipe_top.json'), 'utf8')); } catch (e) { recipe = {}; }
      recipe = Object.assign({}, recipe, {
        recipe_id: 'ui_console', source: 'PolyTwin console (' + sess.login_id + ')',
        target_contact_force_n: params.force, rpm: params.rpm, feed_speed_mm_s: params.feed_mm_s,
        step_over_spacing_ratio: Math.max(0.05, Math.min(1.0, 1 - params.overlap / 100)),
        n_passes: recipe.n_passes || 2,
      });
      fs.mkdirSync(OUT, { recursive: true });
      const recipePath = path.join(OUT, 'ui_recipe.json');
      fs.writeFileSync(recipePath, JSON.stringify(recipe, null, 1));
      try { fs.unlinkSync(feed); } catch (e) { /* 없어도 됨 */ }
      try { fs.unlinkSync(path.join(OUT, 'last_run.json')); } catch (e) { /* 없어도 됨 */ }
      const env = Object.assign({}, process.env, {
        POLISH_RL: '1', POLISH_MONITOR_FEED: feed, POLISH_RL_RECIPE_TOP: recipePath, POLISH_RL_RECIPE_SIDE: recipePath,
        POLISH_RL_OUT: path.join(OUT, 'ui_cells.csv'), POLISH_RENDER_EVERY: '10', POLISH_ROS_PUBLISH: '0',
        POLISH_ROS_CAMERAS: '0', MAX_SIM_STEPS: String(params.max_steps), POLISH_EXIT_WHEN_DONE: '1',
        POLISH_PHYSICAL_CONTACT: params.physical ? '1' : '0',
        /* 콘솔 배치 → v5 (sim_worker.layout_env 와 동일 규칙) */
        POLISH_ROBOTS: ({ 1: 'C', 2: 'SL,SR' })[Number(params.robotCount)] || 'C,SL,SR',
        POLISH_RAIL: params.hasRail === false ? '0' : '1', POLISH_LIFT: params.hasLift === false ? '0' : '1',
        POLISH_PAD_RADIUS: (Number(params.pad || 110) / 2000).toFixed(4),
        POLISH_CAR_LIFT_Z: (0.90 + Number(params.carLift || 0) / 1000).toFixed(3),
        POLISH_RECORD: path.join(OUT, 'run_local_' + Date.now() + '.sqlite'),
      });
      const args = [ 'polishing_v5.py', '--obj_name', 'car', '--headless' ];
      if (body.dry_run) return json(res, 200, { ok: true, dry_run: true, cmd: ISAAC + ' ' + args.join(' '), cwd: path.join(REPO, 'scripts'), recipe, feed });
      const logPath = path.join(OUT, 'sim_run.log');
      const logFd = fs.openSync(logPath, 'w');
      let proc;
      try {
        proc = spawn(ISAAC, args, { cwd: path.join(REPO, 'scripts'), env, detached: true, stdio: ['ignore', logFd, logFd] });
      } catch (e) {
        return json(res, 500, { error: '시뮬레이션을 시작하지 못했습니다: ' + e.message });
      }
      S.proc = proc; S.pid = proc.pid; S.startedAt = Date.now(); S.params = params; S.exitCode = null; S.log = logPath;
      proc.on('exit', (code) => { S.exitCode = code === null ? -1 : code; });
      proc.unref();
      await store.log(sess.login_id, 'sim.start', String(proc.pid), JSON.stringify(params));
      return json(res, 201, { ok: true, pid: proc.pid, params, recipe, feed, log: logPath });
    }
    return json(res, 404, { error: '없는 요청입니다.' });
  }
  /* ── 브라우저 ← 시뮬 기록 (리플레이) ── */
  if (pathname.indexOf('/api/runs') === 0) {
    const sess = await sessionOf(req);
    if (!sess) return json(res, 401, { error: '로그인이 필요합니다.' });
    const mm = pathname.match(/^\/api\/runs(?:\/(\d+)(?:\/(chunks|events|cells))?|\/import)?$/);
    if (!mm) return json(res, 404, { error: 'not found' });
    const runPublic = (r) => ({ id: r.id, job_id: r.job_id, name: r.name, status: r.status, t_sim_end: Number(r.t_sim_end || 0),
      n_frames: Number(r.n_frames || 0), created_at: Number(r.created_at), finished_at: r.finished_at ? Number(r.finished_at) : null,
      meta: (() => { try { return JSON.parse(r.meta || '{}'); } catch { return {}; } })(),
      result: (() => { try { return r.result ? JSON.parse(r.result) : null; } catch { return null; } })() });
    if (pathname === '/api/runs/import' && method === 'POST') {
      /* 로컬 전용: 기록 sqlite 파일을 서버 DB 로 복사한다 (Vercel 은 워커 업로드 경로만) */
      if (process.env.VERCEL) return json(res, 501, { error: '배포 서버에서는 워커 업로드만 지원합니다.' });
      const body = await readBody(req);
      const file = String(body.path || '');
      if (!file || !require('node:fs').existsSync(file)) return json(res, 400, { error: '파일이 없습니다.' });
      const { DatabaseSync } = require('node:sqlite');
      const src = new DatabaseSync(file, { readOnly: true });
      const meta = {}; for (const r of src.prepare('SELECT key, value FROM meta').all()) { try { meta[r.key] = JSON.parse(r.value); } catch { meta[r.key] = r.value; } }
      const id = await store.createRun({ jobId: body.job_id != null ? Number(body.job_id) : null, name: String(body.name || require('node:path').basename(file)), meta });
      const chunks = src.prepare('SELECT seq, t0, t1, n, data FROM chunks ORDER BY seq').all();
      for (let i = 0; i < chunks.length; i += 200) await store.appendChunks(id, chunks.slice(i, i + 200).map((c) => ({ ...c, data: Buffer.from(c.data) })));
      await store.addRunEvents(id, src.prepare('SELECT id, t, robot, level, msg FROM events ORDER BY id').all());
      await store.addRunCells(id, src.prepare('SELECT id, t, data FROM cells ORDER BY id').all().map((c) => ({ ...c, data: Buffer.from(c.data) })));
      const rr = src.prepare('SELECT data FROM result WHERE id = 1').get();
      let result = null; try { result = rr ? JSON.parse(rr.data) : null; } catch { result = null; }
      await store.finishRun(id, 'done', result);
      src.close();
      return json(res, 200, { ok: true, run: runPublic(await store.getRun(id)), chunks: chunks.length });
    }
    if (!mm[1] && method === 'GET') return json(res, 200, { runs: (await store.listRuns(50)).map(runPublic) });
    const run = mm[1] ? await store.getRun(Number(mm[1])) : null;
    if (!run) return json(res, 404, { error: 'run not found' });
    if (!mm[2] && method === 'GET') return json(res, 200, { run: runPublic(run), last_seq: await store.lastChunkSeq(run.id) });
    if (mm[2] === 'chunks' && method === 'GET') {
      const u = new URL(req.url, 'http://x');
      const from = Number(u.searchParams.get('from') || 0), to = Number(u.searchParams.get('to') || (from + 30));
      const rows = await store.getChunks(run.id, from, to, 120);
      return json(res, 200, { run_id: run.id, from, to, chunks: rows.map((c) => ({ seq: Number(c.seq), t0: Number(c.t0), t1: Number(c.t1), n: Number(c.n),
        data: Buffer.from(c.data).toString('base64') })) });
    }
    if (mm[2] === 'events' && method === 'GET') return json(res, 200, { events: await store.getRunEvents(run.id) });
    if (mm[2] === 'cells' && method === 'GET') {
      const u = new URL(req.url, 'http://x');
      const rows = await store.getRunCells(run.id, Number(u.searchParams.get('after') || 0), 20);
      return json(res, 200, { cells: rows.map((c) => ({ id: Number(c.id), t: Number(c.t), data: Buffer.from(c.data).toString('base64') })) });
    }
    return json(res, 405, { error: 'method' });
  }

  if (pathname === '/api/monitor' && method === 'GET') {
    const sess = await sessionOf(req);
    if (!sess) return json(res, 401, { error: '로그인이 필요합니다.' });
    if (simMode() === 'queue') {
      /* 배포/큐 모드: 워커가 POST /api/sim/jobs/:id/feed 로 올린 최신 스냅샷 */
      const row = await store.getState('feed');
      if (!row) return json(res, 200, { live: false, age_s: null, feed: null });
      let data = null; try { data = JSON.parse(row.payload); } catch { data = null; }
      const age = (Date.now() - Number(row.updated_at)) / 1000;
      const cur = await store.latestJob();
      const running = !!cur && cur.status === 'running';
      return json(res, 200, { live: !!data && age < 8 && running, age_s: Math.round(age * 10) / 10, feed: data });
    }
    const fs = require('fs'), path = require('path');
    const feed = process.env.PT_MONITOR_FEED
      || path.join(__dirname, '..', '..', 'cacadaca', 'learning', 'ui_bridge', 'out', 'monitor_feed.json');
    try {
      const raw = fs.readFileSync(feed, 'utf8');
      const data = JSON.parse(raw);
      const age = Date.now() / 1000 - Number(data.ts || 0);
      return json(res, 200, { live: age < 5, age_s: Math.round(age * 10) / 10, feed: data });
    } catch (e) {
      return json(res, 200, { live: false, age_s: null, feed: null });
    }
  }
  if (pathname.indexOf('/api/dataset/') === 0) {
    const sess = await sessionOf(req);
    if (!sess) return json(res, 401, { error: '로그인이 필요합니다.' });
    if (sess.status !== 'active') return json(res, 403, { error: '승인 대기 중인 계정입니다.' });
    if (method !== 'GET') return json(res, 405, { error: '지원하지 않는 요청입니다.' });

    if (pathname === '/api/dataset/seg-best-kpi') {
      const meta = await store.getMeta('seg_best_kpi');
      const rows = await store.listSegments();
      if (!meta && !rows.length) {
        return json(res, 503, { error: '숙련공 정답 데이터가 아직 시드되지 않았습니다 (npm run seed:data).' });
      }
      let head = {};
      try { head = meta ? JSON.parse(meta.payload) : {}; } catch { head = {}; }
      const segments = rows.map((r) => { try { return JSON.parse(r.payload); } catch { return null; } })
        .filter(Boolean);
      return json(res, 200, { ...head, segments });
    }

    if (pathname === '/api/dataset/quality-kpi') {
      const meta = await store.getMeta('quality_kpi');
      if (!meta) {
        return json(res, 503, { error: '품질 기준 데이터가 아직 시드되지 않았습니다 (npm run seed:data).' });
      }
      let body = {};
      try { body = JSON.parse(meta.payload); } catch { body = {}; }
      return json(res, 200, body);
    }

    return json(res, 404, { error: '없는 데이터셋입니다.' });
  }

  /* ══ 숙련공 데이터 라이브러리 ═════════════════════════════
     ① 콘솔이 합격시킨 기록을 쓰고 ④ 라이브러리가 읽는다.
     예전에는 localStorage 'polytwin_saved' 였다 — 브라우저 하나에
     갇혀 있어서 다른 PC 로 가면 사라지고 저장자도 알 수 없었다.
     읽기는 로그인한 전원 공유, 지우기는 본인 또는 admin. ══ */
  if (pathname === '/api/library' || pathname.indexOf('/api/library/') === 0) {
    const sess = await sessionOf(req);
    if (!sess) return json(res, 401, { error: '로그인이 필요합니다.' });
    if (sess.status !== 'active') return json(res, 403, { error: '승인 대기 중인 계정입니다.' });

    if (pathname === '/api/library' && method === 'GET') {
      const rows = await store.listLibrary(200);
      return json(res, 200, { entries: rows.map(publicEntry) });
    }

    if (pathname === '/api/library' && method === 'POST') {
      /* ref(세그먼트 요약 스냅샷)까지 통째로 온다 — 한 건 약 7KB.
         기본 64KB 로는 여유가 빠듯해 이 경로만 올린다 */
      const body = await readBody(req, 256 * 1024);
      const refId = String(body.id || '').trim();
      const seg = String(body.seg || '').trim();
      const name = String(body.name || '').trim();

      if (!refId || refId.length > 64) return json(res, 400, { error: '기록 ID가 올바르지 않습니다.' });
      if (!body.ref || !body.rl) return json(res, 400, { error: '저장할 기록이 비어 있습니다.' });
      if (name.length > 200) return json(res, 400, { error: '이름이 너무 깁니다.' });

      /* 클라이언트가 보낸 것 중 라이브러리가 실제로 읽는 것만 남긴다 */
      const payload = JSON.stringify({ env: body.env || null, rl: body.rl, ref: body.ref });
      if (payload.length > 200 * 1024) return json(res, 413, { error: '기록이 너무 큽니다.' });

      const { entry, created } = await store.createLibraryEntry({
        userId: Number(sess.id), refId, seg, name, payload,
      });
      if (created) await store.log(sess.login_id, 'library.save', refId, seg);
      return json(res, created ? 201 : 200, {
        entry: publicEntry({
          ...entry, owner_login: sess.login_id, owner_name: sess.name,
        }),
        created,
      });
    }

    const m = pathname.match(/^\/api\/library\/(\d+)$/);
    if (m && method === 'DELETE') {
      const id = Number(m[1]);
      const row = await store.findLibraryEntry(id);
      if (!row) return json(res, 404, { error: '없는 기록입니다.' });
      const mine = Number(row.user_id) === Number(sess.id);
      if (!mine && sess.role !== 'admin') {
        return json(res, 403, { error: '본인이 저장한 기록만 지울 수 있습니다.' });
      }
      await store.deleteLibraryEntry(id);
      await store.log(sess.login_id, 'library.delete', String(row.ref_id), mine ? '' : 'by admin');
      return json(res, 200, { ok: true });
    }

    return json(res, 405, { error: '지원하지 않는 요청입니다.' });
  }

  /* ══ 관리자 전용 ══════════════════════════════════════════ */
  if (pathname.indexOf('/api/admin/') === 0) {
    const sess = await sessionOf(req);
    if (!sess) return json(res, 401, { error: '로그인이 필요합니다.' });
    if (sess.role !== 'admin' || sess.status !== 'active') {
      return json(res, 403, { error: '관리자 권한이 필요합니다.' });
    }

    if (pathname === '/api/admin/users' && method === 'GET') {
      return json(res, 200, { users: (await store.listUsers()).map(publicUser) });
    }

    if (pathname === '/api/admin/audit' && method === 'GET') {
      return json(res, 200, { entries: await store.recentAudit(60) });
    }

    const m = pathname.match(/^\/api\/admin\/users\/(\d+)$/);
    if (m) {
      const id = Number(m[1]);
      const target = await store.findById(id);
      if (!target) return json(res, 404, { error: '없는 계정입니다.' });

      if (method === 'PATCH') {
        const body = await readBody(req);
        const changes = [];

        if (body.status !== undefined) {
          if (['pending', 'active', 'suspended'].indexOf(body.status) < 0) {
            return json(res, 400, { error: '알 수 없는 상태입니다.' });
          }
          /* 마지막 관리자를 스스로 잠그지 못하게 한다 */
          if (target.role === 'admin' && target.status === 'active' && body.status !== 'active'
            && (await store.activeAdminCount()) <= 1) {
            return json(res, 409, { error: '활성 관리자가 한 명뿐입니다. 먼저 다른 관리자를 지정하세요.' });
          }
          await store.setStatus(id, body.status);
          if (body.status !== 'active') await store.dropSessionsOfUser(id);
          changes.push('status=' + body.status);
        }

        if (body.role !== undefined) {
          if (['admin', 'engineer'].indexOf(body.role) < 0) {
            return json(res, 400, { error: '알 수 없는 역할입니다.' });
          }
          if (target.role === 'admin' && body.role !== 'admin' && (await store.activeAdminCount()) <= 1) {
            return json(res, 409, { error: '활성 관리자가 한 명뿐입니다. 먼저 다른 관리자를 지정하세요.' });
          }
          await store.setRole(id, body.role);
          changes.push('role=' + body.role);
        }

        if (body.password !== undefined) {
          if (String(body.password).length < 8) {
            return json(res, 400, { error: '비밀번호는 8자 이상이어야 합니다.' });
          }
          await store.setPassword(id, String(body.password));
          await store.dropSessionsOfUser(id);   /* 비번을 바꾸면 기존 세션은 끊는다 */
          changes.push('password reset');
        }

        if (!changes.length) return json(res, 400, { error: '바꿀 항목이 없습니다.' });
        await store.log(sess.login_id, 'admin.update', target.login_id, changes.join(', '));
        return json(res, 200, { user: publicUser(await store.findById(id)) });
      }

      if (method === 'DELETE') {
        if (target.id === sess.id) return json(res, 409, { error: '자기 계정은 삭제할 수 없습니다.' });
        if (target.role === 'admin' && target.status === 'active' && (await store.activeAdminCount()) <= 1) {
          return json(res, 409, { error: '활성 관리자가 한 명뿐입니다.' });
        }
        await store.deleteUser(id);
        await store.log(sess.login_id, 'admin.delete', target.login_id, '');
        return json(res, 200, { ok: true });
      }
    }

    return json(res, 404, { error: '없는 경로입니다.' });
  }

  return json(res, 404, { error: '없는 경로입니다.' });
}

/* ── 관리자 계정 씨앗 ─────────────────────────────────────────
   로컬: server.js 가 기동 시 부른다 (기본값 허용 — 데모).
   Turso: PT_ADMIN_PW 없이는 거부한다 — 기본 비밀번호를 공개
   서버에 두는 사고를 원천 차단. scripts/seed-admin.mjs 로 실행. */
async function seedAdmin() {
  const loginId = process.env.PT_ADMIN_ID || 'admin';
  const password = process.env.PT_ADMIN_PW || 'polytwin2026';
  if (process.env.TURSO_DATABASE_URL && !process.env.PT_ADMIN_PW) {
    throw new Error('원격 DB 에는 PT_ADMIN_PW 를 명시해야 시드합니다 — 기본 비밀번호 금지.');
  }
  if (await store.findByLogin(loginId)) return { loginId, created: false };
  await store.createUser({ loginId, name: '시스템 관리자', password, role: 'admin', status: 'active' });
  await store.log('system', 'seed.admin', loginId, '');
  return { loginId, password, created: true };
}

module.exports = {
  handleApi, sessionOf, seedAdmin, json,
  COOKIE, SESSION_TTL, parseCookies, publicUser,
};
